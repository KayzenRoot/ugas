"""Deterministic, profile-agnostic motion-track sampling.

The motion quality layer operates on scalar and two-component vector values only.
It never inspects pixels or images.  Cubic Hermite tangents use deterministic
finite differences in frame space: one-sided at the endpoints and centered at
interior keyframes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from bisect import bisect_right
from typing import Any, Mapping, Sequence


class MotionCurveError(ValueError):
    """Raised when a motion-track contract or sample cannot be satisfied."""


INTERPOLATIONS = {"linear", "smoothstep", "cubic_hermite"}
VALUE_TYPES = {"scalar", "vec2"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _value(value: Any, value_type: str) -> float | list[float]:
    if value_type == "scalar":
        if not _finite_number(value):
            raise MotionCurveError("motion_track_value_must_be_finite_scalar")
        return float(value)
    if value_type == "vec2":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2 or not all(_finite_number(item) for item in value):
            raise MotionCurveError("motion_track_value_must_be_finite_vec2")
        return [float(value[0]), float(value[1])]
    raise MotionCurveError("motion_track_value_type_invalid")


def _add(first: float | list[float], second: float | list[float]) -> float | list[float]:
    if isinstance(first, list):
        return [first[index] + second[index] for index in range(2)]  # type: ignore[index]
    return float(first) + float(second)  # type: ignore[arg-type]


def _scale(value: float | list[float], factor: float) -> float | list[float]:
    if isinstance(value, list):
        return [component * factor for component in value]
    return float(value) * factor


def _lerp(first: float | list[float], second: float | list[float], factor: float) -> float | list[float]:
    return _add(_scale(first, 1.0 - factor), _scale(second, factor))


def _track_without_timeline(track: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(track, Mapping):
        raise MotionCurveError("motion_track_must_be_an_object")
    track_id = track.get("track_id")
    if not isinstance(track_id, str) or not track_id:
        raise MotionCurveError("motion_track_id_required")
    value_type = track.get("value_type")
    if value_type not in VALUE_TYPES:
        raise MotionCurveError("motion_track_value_type_invalid")
    if track.get("interpolation") not in INTERPOLATIONS:
        raise MotionCurveError("motion_track_interpolation_invalid")
    keyframes = track.get("keyframes")
    if not isinstance(keyframes, list) or len(keyframes) < 2:
        raise MotionCurveError("motion_track_requires_two_or_more_keyframes")
    previous_frame: int | None = None
    normalized: list[dict[str, Any]] = []
    for keyframe in keyframes:
        if not isinstance(keyframe, Mapping):
            raise MotionCurveError("motion_keyframe_must_be_an_object")
        frame = keyframe.get("frame")
        if not isinstance(frame, int) or isinstance(frame, bool) or frame < 0:
            raise MotionCurveError("motion_keyframe_frame_invalid")
        if previous_frame is not None and frame <= previous_frame:
            raise MotionCurveError("motion_keyframes_must_be_strictly_increasing")
        previous_frame = frame
        normalized.append({"frame": frame, "value": _value(keyframe.get("value"), str(value_type))})
    clamp_policy = track.get("clamp_policy")
    if clamp_policy not in (None, "clamp"):
        raise MotionCurveError("motion_track_clamp_policy_invalid")
    return str(value_type), normalized


def validate_motion_tracks(spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate and return a deep copy of the optional track list.

    Keyframe frames are checked against ``spec.frame_count``.  Missing
    ``clamp_policy`` means out-of-range sampling fails closed; ``clamp`` is
    the only explicit policy that permits endpoint clamping.
    """
    tracks = spec.get("motion_tracks", [])
    if not isinstance(tracks, list):
        raise MotionCurveError("motion_tracks_must_be_an_array")
    frame_count = spec.get("frame_count")
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise MotionCurveError("motion_tracks_require_valid_frame_count")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for track in tracks:
        value_type, keyframes = _track_without_timeline(track)
        track_id = str(track["track_id"])
        if track_id in seen:
            raise MotionCurveError("motion_track_id_must_be_unique")
        seen.add(track_id)
        if any(keyframe["frame"] >= frame_count for keyframe in keyframes):
            raise MotionCurveError("motion_keyframe_frame_out_of_range")
        item = {"track_id": track_id, "value_type": value_type, "interpolation": str(track["interpolation"]), "keyframes": keyframes}
        if track.get("clamp_policy") is not None:
            item["clamp_policy"] = track["clamp_policy"]
        normalized.append(item)
    return normalized


def _tangent(values: list[float | list[float]], frames: list[int], index: int) -> float | list[float]:
    if index == 0:
        return _scale(_add(values[1], _scale(values[0], -1.0)), 1.0 / (frames[1] - frames[0]))
    if index == len(values) - 1:
        return _scale(_add(values[-1], _scale(values[-2], -1.0)), 1.0 / (frames[-1] - frames[-2]))
    return _scale(_add(values[index + 1], _scale(values[index - 1], -1.0)), 1.0 / (frames[index + 1] - frames[index - 1]))


def sample_track(track: Mapping[str, Any], frame_float: float) -> float | list[float]:
    """Sample one track at a frame coordinate without internal rounding."""
    if not _finite_number(frame_float):
        raise MotionCurveError("motion_sample_frame_must_be_finite")
    value_type, keyframes = _track_without_timeline(track)
    frame = float(frame_float)
    first, last = keyframes[0]["frame"], keyframes[-1]["frame"]
    if frame < first or frame > last:
        if track.get("clamp_policy") == "clamp":
            return copy.deepcopy(keyframes[0]["value"] if frame < first else keyframes[-1]["value"])
        raise MotionCurveError("motion_sample_out_of_range")
    frames = [int(item["frame"]) for item in keyframes]
    values = [item["value"] for item in keyframes]
    for keyframe in keyframes:
        if frame == float(keyframe["frame"]):
            return copy.deepcopy(keyframe["value"])
    right = bisect_right(frames, frame)
    left_index = right - 1
    right_index = right
    f0, f1 = frames[left_index], frames[right_index]
    t = (frame - f0) / (f1 - f0)
    interpolation = str(track["interpolation"])
    if interpolation == "linear":
        return _lerp(values[left_index], values[right_index], t)
    if interpolation == "smoothstep":
        smooth = t * t * (3.0 - 2.0 * t)
        return _lerp(values[left_index], values[right_index], smooth)
    tangents = [_tangent(values, frames, index) for index in range(len(values))]
    dt = float(f1 - f0)
    h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
    h10 = t**3 - 2.0 * t**2 + t
    h01 = -2.0 * t**3 + 3.0 * t**2
    h11 = t**3 - t**2
    result = _add(_add(_scale(values[left_index], h00), _scale(tangents[left_index], h10 * dt)), _add(_scale(values[right_index], h01), _scale(tangents[right_index], h11 * dt)))
    return _value(result, value_type)


def sample_all_tracks(spec: Mapping[str, Any], frame_float: float) -> dict[str, float | list[float]]:
    """Sample all tracks in declared order, keyed by opaque track ID."""
    return {track["track_id"]: sample_track(track, frame_float) for track in validate_motion_tracks(spec)}


def motion_tracks_sha256(spec: Mapping[str, Any]) -> str:
    """Hash the canonical normalized track list, including interpolation policy."""
    tracks = validate_motion_tracks(spec)
    return hashlib.sha256(canonical_json(tracks).encode("utf-8")).hexdigest()
