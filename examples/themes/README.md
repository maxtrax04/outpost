# Example themes

Themes here are not built into the image. They show how to add your own theme without rebuilding.

To try `sonar`, copy its folder into the folder you mount at `/config/themes`, then open
`http://localhost:8088/?theme=sonar` or pick "Sonar" with the on-screen switcher:

```bash
mkdir -p themes
cp -r examples/themes/sonar themes/
```

See "Adding themes without rebuilding" in [docs/themes.md](../../docs/themes.md).
