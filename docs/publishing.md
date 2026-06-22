# Publishing

GitHub source is published at:

```text
https://github.com/teamslop/preppergpt
```

To publish npm manually:

```bash
npm login
npm whoami
npm run check
npm publish --access public
```

To publish from GitHub Actions:

1. Create an npm automation token.
2. Add it as the repository secret `NPM_TOKEN`.
3. Push a SemVer tag such as `v0.1.0`.

The release workflow runs tests and publishes `preppergpt` with npm provenance.
