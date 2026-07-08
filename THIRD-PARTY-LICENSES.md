# Third-Party License Notes

This project is licensed under Apache-2.0. The runtime dependencies below are third-party packages
and keep their own licenses.

| Package | Verified version | License evidence |
|---------|------------------|------------------|
| `tiktoken` | 0.12.0 | Installed package metadata reports `MIT License`. |
| `fastmcp` | 3.2.4 | Installed package metadata reports `License-Expression: Apache-2.0`. |

Verification command used:

```bash
python -m pip show tiktoken fastmcp
```

Before publishing public distributions, re-run the license check against the exact locked dependency
set and include transitive dependency license review in the release checklist.
