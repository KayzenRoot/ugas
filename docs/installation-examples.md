# Installation examples

The tracked examples demonstrate the consumer contract without pretending to be complete games:

- `examples/consumer-godot-2d` uses `project.godot` and `topdown-rpg-mmorpg-2d`;
- `examples/consumer-space-idle-2d` uses a minimal package marker and `space-idle-strategy-2d`;
- `examples/consumer-generic-3d` uses a minimal custom project and `stylized-3d`.

Recreate their metadata with:

```powershell
python scripts/examples/bootstrap_examples.py --force
```

Review the generated `.game-assets/INSTALLATION-REVIEW.md` in each example before using it as a template for a real project.
