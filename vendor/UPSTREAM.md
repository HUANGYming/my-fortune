# Algorithm provenance

Python calculations adapt selected MIT TaiBu Core rules from
https://github.com/hhszzzz/taibu/tree/4b2a51a/packages/core (version 4.1.0).
The retained taibu-core/LICENSE, THIRD_PARTY_NOTICES.md and ALGORITHM_RULES.md
record attribution and original conventions. Runtime TypeScript and Node
bridge code have been removed. Only selected business algorithms are ported.

Calendar calculations use 6tail/lunar-python 1.4.9 (MIT), the same author's
Python counterpart of upstream lunar-javascript. Apparent solar time uses
Python astronomy-engine 2.1.19 (MIT), matching the upstream engine version.
Their license texts are retained alongside this file.

The 20 captured upstream contexts in tests/fixtures/taibu_reference.json are
synthetic comparison data captured before removing the Node implementation.
See docs/PYTHON_MIGRATION.md for outputs and limitations.
