\# Stage 2.1 Experimental Data Contract Implementation Plan



> \*\*For agentic workers:\*\* REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- \[ ]`) syntax for tracking.



\*\*Goal:\*\* Build and freeze a versioned, testable experimental-session data contract for P0, P2C, L0, and L2C without implementing any experimental condition, Fitts outcome, participant-performance analysis, or model training.



\*\*Architecture:\*\* Add a new isolated `pc/experiment/` package. Contract definitions, machine-readable manifest schema, CSV schemas, validation, synthetic fixtures, and session hashing live here. Existing `pc/receiver`, `pc/clock\_sync`, and `pc/cursor\_preview` remain unchanged and retain their current engineering roles.



\*\*Tech Stack:\*\* Python 3 standard library, JSON, CSV, `hashlib`, `dataclasses`, `pathlib`, `argparse`, pytest.



\*\*Spec:\*\* `docs/superpowers/specs/2026-09-17-stage2-1-experimental-data-contract-design.md`



\## Global Constraints



\* Formal experimental code lives under `pc/experiment/`.

\* `pc/cursor\_preview` remains engineering-preview infrastructure and is not the participant experiment.

\* Allowed condition codes are exactly `P0`, `P2C`, `L0`, and `L2C`.

\* Dataset roles are `development`, `pilot`, `evaluation`, and `synthetic`.

\* Raw Android IMU remains at its native observed acquisition rate.

\* Stage 2.1 must not freeze a final IMU resampling frequency.

\* Stage 2.1 must not define final Fitts throughput, effective-width, movement-onset, overshoot, or endpoint-error algorithms.

\* Raw evidence is immutable after session finalization.

\* Participant identifiers are pseudonymous; direct identifying information must not enter experimental files.

\* Real participant data must not be committed to Git.

\* `participant\_data/` must remain untracked.

\* Development, pilot, evaluation, and synthetic data roles must remain distinguishable.

\* No P0, P2C, L0, L2C mapping algorithm is implemented in Stage 2.1.

\* No real participant data are collected during Stage 2.1.

\* Existing untracked M2/M2.3 diagnostic evidence must not be added or deleted.

\* Do not use `git add .`.

\* Each task must end with tests passing before its commit.



\---



\## File Structure



Stage 2.1 will produce:



```text

pc/

└── experiment/

&#x20;   ├── \_\_init\_\_.py

&#x20;   ├── contracts.py

&#x20;   ├── csv\_schema.py

&#x20;   ├── manifest.py

&#x20;   ├── validator.py

&#x20;   ├── session\_hash.py

&#x20;   ├── cli.py

&#x20;   ├── schemas/

&#x20;   │   └── manifest.schema.json

&#x20;   └── tests/

&#x20;       ├── \_\_init\_\_.py

&#x20;       ├── fixture\_builder.py

&#x20;       ├── test\_contracts.py

&#x20;       ├── test\_csv\_schema.py

&#x20;       ├── test\_manifest.py

&#x20;       ├── test\_validator.py

&#x20;       ├── test\_session\_hash.py

&#x20;       └── test\_cli.py



docs/

├── decisions/

│   └── stage2\_1\_experimental\_data\_contract\_v1\_0.md

└── superpowers/

&#x20;   └── plans/

&#x20;       └── 2026-09-17-stage2-1-experimental-data-contract.md

```



The implementation uses no third-party runtime validation dependency. The JSON Schema file is the machine-readable contract artifact; Python validation remains explicit and testable using the standard library.



\---



\# Task 1: Package Skeleton and Authoritative Contract Constants



\*\*Files:\*\*



\* Create: `pc/experiment/\_\_init\_\_.py`

\* Create: `pc/experiment/contracts.py`

\* Create: `pc/experiment/tests/\_\_init\_\_.py`

\* Create: `pc/experiment/tests/test\_contracts.py`

\* Modify: `.gitignore`



\*\*Interfaces:\*\*



Produces:



```python

SCHEMA\_VERSION: str

ALLOWED\_DATASET\_ROLES: frozenset\[str]

ALLOWED\_SESSION\_STATUSES: frozenset\[str]

ALLOWED\_CONDITIONS: frozenset\[str]

ALLOWED\_EVENT\_TYPES: frozenset\[str]

```



Later tasks import these values rather than duplicating vocabularies.



\* \[ ] \*\*Step 1: Write the failing contract tests\*\*



Create `pc/experiment/tests/test\_contracts.py`:



```python

from pc.experiment.contracts import (

&#x20;   ALLOWED\_CONDITIONS,

&#x20;   ALLOWED\_DATASET\_ROLES,

&#x20;   ALLOWED\_EVENT\_TYPES,

&#x20;   ALLOWED\_SESSION\_STATUSES,

&#x20;   SCHEMA\_VERSION,

)





def test\_schema\_version\_is\_1\_0():

&#x20;   assert SCHEMA\_VERSION == "1.0"





def test\_allowed\_conditions\_are\_frozen():

&#x20;   assert ALLOWED\_CONDITIONS == frozenset(

&#x20;       {"P0", "P2C", "L0", "L2C"}

&#x20;   )





def test\_dataset\_roles\_are\_frozen():

&#x20;   assert ALLOWED\_DATASET\_ROLES == frozenset(

&#x20;       {"development", "pilot", "evaluation", "synthetic"}

&#x20;   )





def test\_session\_statuses\_are\_frozen():

&#x20;   assert ALLOWED\_SESSION\_STATUSES == frozenset(

&#x20;       {"open", "closed"}

&#x20;   )





def test\_event\_vocabulary\_is\_frozen():

&#x20;   assert ALLOWED\_EVENT\_TYPES == frozenset(

&#x20;       {

&#x20;           "session\_start",

&#x20;           "session\_end",

&#x20;           "condition\_start",

&#x20;           "condition\_end",

&#x20;           "block\_start",

&#x20;           "block\_end",

&#x20;           "sequence\_start",

&#x20;           "sequence\_end",

&#x20;           "trial\_start",

&#x20;           "target\_onset",

&#x20;           "selection",

&#x20;           "trial\_complete",

&#x20;           "trial\_abort",

&#x20;           "calibration\_start",

&#x20;           "calibration\_end",

&#x20;       }

&#x20;   )

```



\* \[ ] \*\*Step 2: Run the test and verify failure\*\*



Run:



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_contracts.py `

&#x20; -v

```



Expected: import/module failure because `pc.experiment.contracts` does not yet exist.



\* \[ ] \*\*Step 3: Implement contract constants\*\*



Create `pc/experiment/\_\_init\_\_.py`:



```python

"""Formal experimental data-contract infrastructure."""

```



Create `pc/experiment/contracts.py`:



```python

SCHEMA\_VERSION = "1.0"



ALLOWED\_DATASET\_ROLES = frozenset(

&#x20;   {

&#x20;       "development",

&#x20;       "pilot",

&#x20;       "evaluation",

&#x20;       "synthetic",

&#x20;   }

)



ALLOWED\_SESSION\_STATUSES = frozenset(

&#x20;   {

&#x20;       "open",

&#x20;       "closed",

&#x20;   }

)



ALLOWED\_CONDITIONS = frozenset(

&#x20;   {

&#x20;       "P0",

&#x20;       "P2C",

&#x20;       "L0",

&#x20;       "L2C",

&#x20;   }

)



ALLOWED\_EVENT\_TYPES = frozenset(

&#x20;   {

&#x20;       "session\_start",

&#x20;       "session\_end",

&#x20;       "condition\_start",

&#x20;       "condition\_end",

&#x20;       "block\_start",

&#x20;       "block\_end",

&#x20;       "sequence\_start",

&#x20;       "sequence\_end",

&#x20;       "trial\_start",

&#x20;       "target\_onset",

&#x20;       "selection",

&#x20;       "trial\_complete",

&#x20;       "trial\_abort",

&#x20;       "calibration\_start",

&#x20;       "calibration\_end",

&#x20;   }

)

```



Create empty:



`pc/experiment/tests/\_\_init\_\_.py`



\* \[ ] \*\*Step 4: Protect participant data\*\*



Add this exact line to `.gitignore`:



```text

participant\_data/

```



Verify it occurs exactly once.



\* \[ ] \*\*Step 5: Run tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_contracts.py `

&#x20; -v

```



Expected: all PASS.



\* \[ ] \*\*Step 6: Verify only intended files changed\*\*



```powershell

git diff --name-status

git diff --check

```



\* \[ ] \*\*Step 7: Commit Task 1\*\*



Stage only:



```powershell

git add `

&#x20; ".gitignore" `

&#x20; "pc/experiment/\_\_init\_\_.py" `

&#x20; "pc/experiment/contracts.py" `

&#x20; "pc/experiment/tests/\_\_init\_\_.py" `

&#x20; "pc/experiment/tests/test\_contracts.py"

```



Commit:



```powershell

git commit `

&#x20; -m "feat(stage2.1): add experiment contract constants"

```



\---



\# Task 2: Freeze CSV Schemas



\*\*Files:\*\*



\* Create: `pc/experiment/csv\_schema.py`

\* Create: `pc/experiment/tests/test\_csv\_schema.py`



\*\*Interfaces:\*\*



Produces:



```python

TRIAL\_EVENT\_COLUMNS: tuple\[str, ...]

CURSOR\_SAMPLE\_COLUMNS: tuple\[str, ...]

CALIBRATION\_EVENT\_COLUMNS: tuple\[str, ...]

QUALITY\_FLAG\_COLUMNS: tuple\[str, ...]

CSV\_SCHEMAS: dict\[str, tuple\[str, ...]]



validate\_header(

&#x20;   actual: list\[str],

&#x20;   expected: tuple\[str, ...],

) -> list\[str]

```



\* \[ ] \*\*Step 1: Write failing tests\*\*



Create `pc/experiment/tests/test\_csv\_schema.py`:



```python

from pc.experiment.csv\_schema import (

&#x20;   CALIBRATION\_EVENT\_COLUMNS,

&#x20;   CURSOR\_SAMPLE\_COLUMNS,

&#x20;   QUALITY\_FLAG\_COLUMNS,

&#x20;   TRIAL\_EVENT\_COLUMNS,

&#x20;   validate\_header,

)





def test\_trial\_event\_columns\_are\_exact():

&#x20;   assert TRIAL\_EVENT\_COLUMNS == (

&#x20;       "event\_id",

&#x20;       "participant\_id",

&#x20;       "session\_id",

&#x20;       "condition\_code",

&#x20;       "block\_id",

&#x20;       "sequence\_id",

&#x20;       "trial\_id",

&#x20;       "event\_type",

&#x20;       "pc\_time\_ns",

&#x20;       "target\_id",

&#x20;       "target\_x\_px",

&#x20;       "target\_y\_px",

&#x20;       "target\_width\_px",

&#x20;       "target\_height\_px",

&#x20;       "pointer\_x\_px",

&#x20;       "pointer\_y\_px",

&#x20;       "event\_note",

&#x20;   )





def test\_cursor\_sample\_columns\_are\_exact():

&#x20;   assert CURSOR\_SAMPLE\_COLUMNS == (

&#x20;       "sample\_id",

&#x20;       "participant\_id",

&#x20;       "session\_id",

&#x20;       "condition\_code",

&#x20;       "block\_id",

&#x20;       "sequence\_id",

&#x20;       "trial\_id",

&#x20;       "pc\_time\_ns",

&#x20;       "cursor\_x\_px",

&#x20;       "cursor\_y\_px",

&#x20;       "active\_target\_id",

&#x20;       "source\_seq\_start",

&#x20;       "source\_seq\_end",

&#x20;   )





def test\_calibration\_event\_columns\_are\_exact():

&#x20;   assert CALIBRATION\_EVENT\_COLUMNS == (

&#x20;       "calibration\_event\_id",

&#x20;       "participant\_id",

&#x20;       "session\_id",

&#x20;       "condition\_code",

&#x20;       "calibration\_id",

&#x20;       "step\_id",

&#x20;       "event\_type",

&#x20;       "pc\_time\_ns",

&#x20;       "reference\_target\_id",

&#x20;       "source\_seq\_start",

&#x20;       "source\_seq\_end",

&#x20;       "instruction\_code",

&#x20;       "event\_note",

&#x20;   )





def test\_quality\_flag\_columns\_are\_exact():

&#x20;   assert QUALITY\_FLAG\_COLUMNS == (

&#x20;       "scope\_type",

&#x20;       "scope\_id",

&#x20;       "flag\_code",

&#x20;       "flag\_value",

&#x20;       "reason",

&#x20;       "rule\_version",

&#x20;       "created\_utc",

&#x20;   )





def test\_header\_validation\_accepts\_exact\_header():

&#x20;   assert validate\_header(

&#x20;       list(TRIAL\_EVENT\_COLUMNS),

&#x20;       TRIAL\_EVENT\_COLUMNS,

&#x20;   ) == \[]





def test\_header\_validation\_rejects\_missing\_column():

&#x20;   actual = list(TRIAL\_EVENT\_COLUMNS\[:-1])



&#x20;   errors = validate\_header(

&#x20;       actual,

&#x20;       TRIAL\_EVENT\_COLUMNS,

&#x20;   )



&#x20;   assert errors

```



These tests intentionally implement the already committed design spec rather than the abandoned semantic patch.



\* \[ ] \*\*Step 2: Verify tests fail\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_csv\_schema.py `

&#x20; -v

```



\* \[ ] \*\*Step 3: Implement `csv\_schema.py`\*\*



```python

TRIAL\_EVENT\_COLUMNS = (

&#x20;   "event\_id",

&#x20;   "participant\_id",

&#x20;   "session\_id",

&#x20;   "condition\_code",

&#x20;   "block\_id",

&#x20;   "sequence\_id",

&#x20;   "trial\_id",

&#x20;   "event\_type",

&#x20;   "pc\_time\_ns",

&#x20;   "target\_id",

&#x20;   "target\_x\_px",

&#x20;   "target\_y\_px",

&#x20;   "target\_width\_px",

&#x20;   "target\_height\_px",

&#x20;   "pointer\_x\_px",

&#x20;   "pointer\_y\_px",

&#x20;   "event\_note",

)



CURSOR\_SAMPLE\_COLUMNS = (

&#x20;   "sample\_id",

&#x20;   "participant\_id",

&#x20;   "session\_id",

&#x20;   "condition\_code",

&#x20;   "block\_id",

&#x20;   "sequence\_id",

&#x20;   "trial\_id",

&#x20;   "pc\_time\_ns",

&#x20;   "cursor\_x\_px",

&#x20;   "cursor\_y\_px",

&#x20;   "active\_target\_id",

&#x20;   "source\_seq\_start",

&#x20;   "source\_seq\_end",

)



CALIBRATION\_EVENT\_COLUMNS = (

&#x20;   "calibration\_event\_id",

&#x20;   "participant\_id",

&#x20;   "session\_id",

&#x20;   "condition\_code",

&#x20;   "calibration\_id",

&#x20;   "step\_id",

&#x20;   "event\_type",

&#x20;   "pc\_time\_ns",

&#x20;   "reference\_target\_id",

&#x20;   "source\_seq\_start",

&#x20;   "source\_seq\_end",

&#x20;   "instruction\_code",

&#x20;   "event\_note",

)



QUALITY\_FLAG\_COLUMNS = (

&#x20;   "scope\_type",

&#x20;   "scope\_id",

&#x20;   "flag\_code",

&#x20;   "flag\_value",

&#x20;   "reason",

&#x20;   "rule\_version",

&#x20;   "created\_utc",

)



CSV\_SCHEMAS = {

&#x20;   "raw/trial\_events.csv": TRIAL\_EVENT\_COLUMNS,

&#x20;   "raw/cursor\_samples.csv": CURSOR\_SAMPLE\_COLUMNS,

&#x20;   "raw/calibration\_events.csv": CALIBRATION\_EVENT\_COLUMNS,

&#x20;   "derived/quality\_flags.csv": QUALITY\_FLAG\_COLUMNS,

}





def validate\_header(

&#x20;   actual: list\[str],

&#x20;   expected: tuple\[str, ...],

) -> list\[str]:

&#x20;   if tuple(actual) == expected:

&#x20;       return \[]



&#x20;   return \[

&#x20;       "CSV header mismatch: "

&#x20;       f"expected={expected!r}, actual={tuple(actual)!r}"

&#x20;   ]

```



\* \[ ] \*\*Step 4: Run Task 1–2 tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_contracts.py `

&#x20; pc/experiment/tests/test\_csv\_schema.py `

&#x20; -v

```



Expected: PASS.



\* \[ ] \*\*Step 5: Commit Task 2\*\*



```powershell

git add `

&#x20; "pc/experiment/csv\_schema.py" `

&#x20; "pc/experiment/tests/test\_csv\_schema.py"



git commit `

&#x20; -m "feat(stage2.1): define experimental CSV schemas"

```



\---



\# Task 3: Machine-Readable Manifest Contract



\*\*Files:\*\*



\* Create: `pc/experiment/schemas/manifest.schema.json`

\* Create: `pc/experiment/manifest.py`

\* Create: `pc/experiment/tests/test\_manifest.py`



\*\*Interfaces:\*\*



Produces:



```python

MANIFEST\_REQUIRED\_FIELDS: tuple\[str, ...]



load\_manifest(path: Path) -> dict\[str, object]



validate\_manifest(

&#x20;   manifest: dict\[str, object],

) -> list\[str]

```



\* \[ ] \*\*Step 1: Write failing tests\*\*



The tests must check:



```python

def test\_valid\_manifest\_has\_no\_errors():

&#x20;   ...





def test\_manifest\_rejects\_wrong\_schema\_version():

&#x20;   ...





def test\_manifest\_rejects\_unknown\_dataset\_role():

&#x20;   ...





def test\_manifest\_rejects\_unknown\_condition():

&#x20;   ...





def test\_manifest\_rejects\_duplicate\_condition\_order():

&#x20;   ...





def test\_manifest\_requires\_closed\_or\_open\_status():

&#x20;   ...





def test\_json\_schema\_required\_fields\_match\_python\_contract():

&#x20;   ...

```



Use this valid manifest base:



```python

VALID\_MANIFEST = {

&#x20;   "schema\_version": "1.0",

&#x20;   "participant\_id": "P7K4M2Q8",

&#x20;   "session\_id": "SYNTHETIC\_SESSION\_001",

&#x20;   "dataset\_role": "synthetic",

&#x20;   "session\_status": "closed",

&#x20;   "experiment\_protocol\_version": "synthetic-v1",

&#x20;   "condition\_order": \["P0", "P2C", "L0", "L2C"],

&#x20;   "functional\_commit": "synthetic",

&#x20;   "experiment\_software\_version": "stage2.1-test",

&#x20;   "device": {

&#x20;       "manufacturer": "synthetic",

&#x20;       "model": "SM-A175F",

&#x20;       "android\_version": "16",

&#x20;       "api\_level": 36,

&#x20;       "android\_session\_id": "SYNTHETIC\_ANDROID\_001",

&#x20;   },

&#x20;   "display": {

&#x20;       "display\_width\_px": 1920,

&#x20;       "display\_height\_px": 1080,

&#x20;       "experiment\_window\_width\_px": 1920,

&#x20;       "experiment\_window\_height\_px": 1080,

&#x20;       "display\_scale\_factor": 1.0,

&#x20;   },

&#x20;   "android\_evidence": {

&#x20;       "imu\_file": "raw/imu/imu.csv",

&#x20;       "imu\_sha256": "0" \* 64,

&#x20;       "android\_metadata\_file": "raw/imu/meta.txt",

&#x20;       "android\_metadata\_sha256": "0" \* 64,

&#x20;   },

&#x20;   "clock\_evidence": {

&#x20;       "clock\_model\_file": "raw/clock/clock\_model.json",

&#x20;       "clock\_model\_sha256": "0" \* 64,

&#x20;       "sync\_probes\_file": "raw/clock/sync\_probes.csv",

&#x20;       "sync\_probes\_sha256": "0" \* 64,

&#x20;   },

&#x20;   "files": \[],

}

```



\* \[ ] \*\*Step 2: Run and verify failure\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_manifest.py `

&#x20; -v

```



\* \[ ] \*\*Step 3: Implement JSON Schema\*\*



`manifest.schema.json` must use:



```json

{

&#x20; "$schema": "https://json-schema.org/draft/2020-12/schema",

&#x20; "$id": "imu-cursor-experiment-manifest-v1.0",

&#x20; "title": "IMU Cursor Experimental Session Manifest",

&#x20; "type": "object",

&#x20; "additionalProperties": false

}

```



It must require exactly the top-level fields established in the committed design:



```text

schema\_version

participant\_id

session\_id

dataset\_role

session\_status

experiment\_protocol\_version

condition\_order

functional\_commit

experiment\_software\_version

device

display

android\_evidence

clock\_evidence

files

```



The machine-readable schema must encode the allowed values for:



```text

schema\_version = "1.0"



dataset\_role =

development | pilot | evaluation | synthetic



session\_status =

open | closed



condition\_order items =

P0 | P2C | L0 | L2C

```



\* \[ ] \*\*Step 4: Implement `manifest.py`\*\*



Validation must explicitly verify:



```python

schema\_version == SCHEMA\_VERSION

dataset\_role in ALLOWED\_DATASET\_ROLES

session\_status in ALLOWED\_SESSION\_STATUSES

condition\_order is list\[str]

condition\_order contains only ALLOWED\_CONDITIONS

condition\_order contains no duplicate condition

all required top-level fields exist

participant\_id is non-empty

session\_id is non-empty

```



Do not add outcome-related validation.



\* \[ ] \*\*Step 5: Run tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_manifest.py `

&#x20; -v

```



\* \[ ] \*\*Step 6: Run all Stage 2.1 tests so far\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests `

&#x20; -v

```



\* \[ ] \*\*Step 7: Commit\*\*



```powershell

git add `

&#x20; "pc/experiment/schemas/manifest.schema.json" `

&#x20; "pc/experiment/manifest.py" `

&#x20; "pc/experiment/tests/test\_manifest.py"



git commit `

&#x20; -m "feat(stage2.1): add session manifest contract"

```



\---



\# Task 4: Cross-File Session Validator



\*\*Files:\*\*



\* Create: `pc/experiment/validator.py`

\* Create: `pc/experiment/tests/fixture\_builder.py`

\* Create: `pc/experiment/tests/test\_validator.py`



\*\*Interfaces:\*\*



Produces:



```python

@dataclass(frozen=True)

class ValidationIssue:

&#x20;   code: str

&#x20;   message: str





@dataclass(frozen=True)

class ValidationReport:

&#x20;   issues: tuple\[ValidationIssue, ...]



&#x20;   @property

&#x20;   def is\_valid(self) -> bool:

&#x20;       ...





def validate\_session(

&#x20;   session\_dir: Path,

) -> ValidationReport:

&#x20;   ...

```



\* \[ ] \*\*Step 1: Build a temporary synthetic fixture helper\*\*



`fixture\_builder.py` must create a temporary session containing:



```text

manifest.json

raw/trial\_events.csv

raw/cursor\_samples.csv

raw/calibration\_events.csv

raw/imu/imu.csv

raw/imu/meta.txt

raw/clock/clock\_model.json

raw/clock/sync\_probes.csv

artifacts/calibration\_parameters.json

artifacts/model\_manifest.json

derived/quality\_flags.csv

```



The synthetic trial/event data must include all four condition codes.



It must contain no real participant information.



\* \[ ] \*\*Step 2: Write failing validator tests\*\*



Required tests:



```python

def test\_valid\_synthetic\_session\_passes():

&#x20;   ...





def test\_missing\_required\_file\_fails():

&#x20;   ...





def test\_manifest\_participant\_mismatch\_fails():

&#x20;   ...





def test\_manifest\_session\_mismatch\_fails():

&#x20;   ...





def test\_invalid\_condition\_code\_fails():

&#x20;   ...





def test\_duplicate\_event\_id\_fails():

&#x20;   ...





def test\_duplicate\_cursor\_sample\_id\_fails():

&#x20;   ...





def test\_invalid\_pc\_time\_ns\_fails():

&#x20;   ...





def test\_decreasing\_cursor\_time\_fails():

&#x20;   ...





def test\_unknown\_trial\_reference\_fails():

&#x20;   ...





def test\_open\_session\_is\_not\_valid\_as\_finalized\_session():

&#x20;   ...

```



\* \[ ] \*\*Step 3: Run and verify failures\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_validator.py `

&#x20; -v

```



\* \[ ] \*\*Step 4: Implement validator\*\*



`validate\_session()` must perform, in this order:



```text

1\. session directory exists

2\. manifest exists and parses

3\. manifest structural validation

4\. required raw CSV files exist

5\. CSV headers exactly match contracts

6\. participant\_id consistency

7\. session\_id consistency

8\. valid condition codes

9\. unique event\_id

10\. unique sample\_id

11\. pc\_time\_ns parses as integer

12\. ordered cursor stream does not decrease in pc\_time\_ns

13\. trial references resolve to known trial IDs

14\. session\_status == closed for finalized-session validation

```



It must report failures; it must never modify source files.



\* \[ ] \*\*Step 5: Run tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_validator.py `

&#x20; -v

```



\* \[ ] \*\*Step 6: Regression test entire package\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests `

&#x20; -v

```



\* \[ ] \*\*Step 7: Commit\*\*



```powershell

git add `

&#x20; "pc/experiment/validator.py" `

&#x20; "pc/experiment/tests/fixture\_builder.py" `

&#x20; "pc/experiment/tests/test\_validator.py"



git commit `

&#x20; -m "feat(stage2.1): validate experimental sessions"

```



\---



\# Task 5: Evidence Hash Validation and Session Finalization



\*\*Files:\*\*



\* Create: `pc/experiment/session\_hash.py`

\* Create: `pc/experiment/tests/test\_session\_hash.py`



\*\*Interfaces:\*\*



Produces:



```python

sha256\_file(path: Path) -> str



generate\_session\_hashes(

&#x20;   session\_dir: Path,

) -> list\[tuple\[str, str]]



write\_session\_hash\_manifest(

&#x20;   session\_dir: Path,

) -> Path



verify\_session\_hash\_manifest(

&#x20;   session\_dir: Path,

) -> list\[str]

```



Hash manifest filename:



```text

SESSION\_SHA256SUMS.txt

```



\* \[ ] \*\*Step 1: Write failing tests\*\*



Required:



```python

def test\_sha256\_file\_is\_deterministic():

&#x20;   ...





def test\_hash\_manifest\_is\_sorted\_by\_relative\_path():

&#x20;   ...





def test\_hash\_manifest\_uses\_relative\_paths():

&#x20;   ...





def test\_hash\_manifest\_excludes\_itself():

&#x20;   ...





def test\_hash\_manifest\_detects\_modified\_file():

&#x20;   ...





def test\_hash\_manifest\_detects\_missing\_file():

&#x20;   ...

```



\* \[ ] \*\*Step 2: Run failing tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_session\_hash.py `

&#x20; -v

```



\* \[ ] \*\*Step 3: Implement SHA-256\*\*



Use:



```python

import hashlib





def sha256\_file(path: Path) -> str:

&#x20;   digest = hashlib.sha256()



&#x20;   with path.open("rb") as handle:

&#x20;       for block in iter(

&#x20;           lambda: handle.read(1024 \* 1024),

&#x20;           b"",

&#x20;       ):

&#x20;           digest.update(block)



&#x20;   return digest.hexdigest().upper()

```



Hash entries use:



```text

<SHA256><two spaces><session-relative-path>

```



Paths in `SESSION\_SHA256SUMS.txt` use forward slashes.



\* \[ ] \*\*Step 4: Preserve raw immutability\*\*



The hash writer must never:



```text

modify raw CSV

modify IMU evidence

modify clock evidence

delete evidence

rewrite manifest contents

```



It may only write:



`SESSION\_SHA256SUMS.txt`



\* \[ ] \*\*Step 5: Run tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_session\_hash.py `

&#x20; -v

```



\* \[ ] \*\*Step 6: Run all experiment tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests `

&#x20; -v

```



\* \[ ] \*\*Step 7: Commit\*\*



```powershell

git add `

&#x20; "pc/experiment/session\_hash.py" `

&#x20; "pc/experiment/tests/test\_session\_hash.py"



git commit `

&#x20; -m "feat(stage2.1): add session evidence hashing"

```



\---



\# Task 6: Command-Line Validator and Finalizer



\*\*Files:\*\*



\* Create: `pc/experiment/cli.py`

\* Create: `pc/experiment/tests/test\_cli.py`



\*\*Interfaces:\*\*



CLI commands:



```text

python -m pc.experiment.cli validate <session-dir>

python -m pc.experiment.cli finalize <session-dir>

python -m pc.experiment.cli verify-hashes <session-dir>

```



Exit codes:



```text

0 = success

1 = validation/hash failure

2 = command/input usage failure

```



\* \[ ] \*\*Step 1: Write failing CLI tests\*\*



Tests must cover:



```python

def test\_validate\_valid\_session\_returns\_zero():

&#x20;   ...





def test\_validate\_invalid\_session\_returns\_one():

&#x20;   ...





def test\_finalize\_invalid\_session\_refuses\_hash\_manifest():

&#x20;   ...





def test\_finalize\_valid\_closed\_session\_writes\_hash\_manifest():

&#x20;   ...





def test\_verify\_hashes\_returns\_zero\_for\_unchanged\_session():

&#x20;   ...





def test\_verify\_hashes\_returns\_one\_after\_evidence\_change():

&#x20;   ...

```



\* \[ ] \*\*Step 2: Run failing tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_cli.py `

&#x20; -v

```



\* \[ ] \*\*Step 3: Implement CLI\*\*



The `finalize` flow must be:



```text

validate\_session

&#x20;   ↓

validation PASS?

&#x20;   ↓ yes

write SESSION\_SHA256SUMS.txt

&#x20;   ↓

verify SESSION\_SHA256SUMS.txt

&#x20;   ↓

return 0

```



If validation fails, no hash manifest may be generated.



\* \[ ] \*\*Step 4: Run CLI tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests/test\_cli.py `

&#x20; -v

```



\* \[ ] \*\*Step 5: Run all Stage 2.1 tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests `

&#x20; -v

```



\* \[ ] \*\*Step 6: Commit\*\*



```powershell

git add `

&#x20; "pc/experiment/cli.py" `

&#x20; "pc/experiment/tests/test\_cli.py"



git commit `

&#x20; -m "feat(stage2.1): add experiment validation CLI"

```



\---



\# Task 7: Synthetic End-to-End Qualification



\*\*Files:\*\*



\* Modify only Stage 2.1 test/fixture infrastructure if a demonstrated defect is found.

\* Do not change frozen contract semantics to make tests easier.



\*\*Interfaces:\*\*



This task demonstrates the complete Stage 2.1 data path without a human participant.



\* \[ ] \*\*Step 1: Run full Stage 2.1 tests\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests `

&#x20; -v

```



Expected: all PASS.



\* \[ ] \*\*Step 2: Generate a valid synthetic session\*\*



Use the fixture-builder entrypoint established in Task 4 or a small test helper to generate:



```text

bench\_data/stage2\_1\_synthetic\_validation/valid\_session/

```



The manifest must contain:



```text

dataset\_role = synthetic

participant\_id = P7K4M2Q8

conditions = P0, P2C, L0, L2C

```



No human data.



\* \[ ] \*\*Step 3: Validate\*\*



```powershell

python -m pc.experiment.cli `

&#x20; validate `

&#x20; "bench\_data/stage2\_1\_synthetic\_validation/valid\_session"

```



Expected:



```text

VALIDATION\_STATUS=PASS

```



Exit code `0`.



\* \[ ] \*\*Step 4: Finalize\*\*



```powershell

python -m pc.experiment.cli `

&#x20; finalize `

&#x20; "bench\_data/stage2\_1\_synthetic\_validation/valid\_session"

```



Expected:



```text

FINALIZATION\_STATUS=PASS

```



and:



```text

SESSION\_SHA256SUMS.txt

```



exists.



\* \[ ] \*\*Step 5: Verify hashes\*\*



```powershell

python -m pc.experiment.cli `

&#x20; verify-hashes `

&#x20; "bench\_data/stage2\_1\_synthetic\_validation/valid\_session"

```



Expected:



```text

HASH\_VERIFY\_STATUS=PASS

```



\* \[ ] \*\*Step 6: Demonstrate expected failure\*\*



Copy the synthetic session to:



```text

bench\_data/stage2\_1\_synthetic\_validation/invalid\_session/

```



Modify only the copied synthetic cursor CSV so that one `condition\_code` becomes:



```text

INVALID

```



Then run:



```powershell

python -m pc.experiment.cli `

&#x20; validate `

&#x20; "bench\_data/stage2\_1\_synthetic\_validation/invalid\_session"

```



Expected:



```text

VALIDATION\_STATUS=FAIL

```



with a condition-code validation error and exit code `1`.



\* \[ ] \*\*Step 7: Preserve synthetic evidence\*\*



Create:



```text

bench\_data/stage2\_1\_synthetic\_validation/VALIDATION\_STATUS.txt

```



It records:



```text

VALID\_SESSION=PASS

VALID\_SESSION\_HASH\_VERIFY=PASS

INVALID\_SESSION=EXPECTED\_FAIL

REAL\_PARTICIPANT\_DATA\_USED=false

SCHEMA\_VERSION=1.0

```



This evidence remains untracked unless a later explicit repository policy says otherwise.



\---



\# Task 8: Freeze Experimental Data Contract v1.0



\*\*Files:\*\*



\* Create: `docs/decisions/stage2\_1\_experimental\_data\_contract\_v1\_0.md`



\*\*Interfaces:\*\*



The decision document freezes what was actually implemented and tested.



\* \[ ] \*\*Step 1: Write decision document\*\*



It must record:



```text

Stage = 2.1

Schema version = 1.0

Design spec path

Implementation-plan path

Allowed dataset roles

Allowed condition codes

Raw CSV schemas

Manifest schema path

Session validator command

Session finalization command

SHA-256 verification command

Synthetic qualification result

No participant data collected

No Fitts metric frozen

No resampling grid frozen

No condition algorithm implemented

```



It must explicitly state:



```text

P0/P2C/L0/L2C codes are frozen as identifiers only.

Their algorithms are not defined by Stage 2.1.

```



\* \[ ] \*\*Step 2: Run complete tests before freezing\*\*



```powershell

python -m pytest `

&#x20; pc/experiment/tests `

&#x20; -v

```



Expected: PASS.



\* \[ ] \*\*Step 3: Run repository-relevant existing tests\*\*



At minimum:



```powershell

python -m pytest `

&#x20; pc/clock\_sync/tests `

&#x20; pc/cursor\_preview/tests `

&#x20; pc/experiment/tests `

&#x20; -v

```



No existing engineering subsystem may regress.



\* \[ ] \*\*Step 4: Check source boundaries\*\*



```powershell

git diff `

&#x20; 82d907bd8820c66708dfa6dfd17e43c663f52a7a..HEAD `

&#x20; --name-status

```



Changes should be limited to:



```text

.gitignore

pc/experiment/\*\*

docs/decisions/stage2\_1\_experimental\_data\_contract\_v1\_0.md

docs/superpowers/plans/2026-09-17-stage2-1-experimental-data-contract.md

```



No modification to:



```text

pc/receiver/\*\*

pc/clock\_sync/\*\*

pc/cursor\_preview/\*\*

android/\*\*

```



\* \[ ] \*\*Step 5: Commit decision document\*\*



```powershell

git add `

&#x20; "docs/decisions/stage2\_1\_experimental\_data\_contract\_v1\_0.md"



git commit `

&#x20; -m "docs(stage2.1): freeze experimental data contract v1.0"

```



\* \[ ] \*\*Step 6: Verify clean tracked state\*\*



```powershell

git diff --name-status

git diff --cached --name-status

```



Both must be empty.



\* \[ ] \*\*Step 7: Tag only after every exit criterion is satisfied\*\*



Tag name:



```text

stage2.1-experimental-data-contract-v1.0

```



Command:



```powershell

git tag `

&#x20; -a `

&#x20; stage2.1-experimental-data-contract-v1.0 `

&#x20; -m "Freeze Stage 2.1 experimental data contract v1.0"

```



Verify:



```powershell

git rev-parse HEAD



git rev-list `

&#x20; -n 1 `

&#x20; stage2.1-experimental-data-contract-v1.0

```



Both hashes must match.



\---



\# Final Stage 2.1 Exit Gate



Stage 2.1 may be declared complete only when all of the following are true:



```text

Design spec committed

Implementation plan committed

participant\_data/ ignored by Git

Contract constants tested

CSV schemas tested

Manifest schema tested

Cross-file validator tested

Session SHA-256 generation tested

Session hash verification tested

CLI tested

Valid synthetic session PASS

Invalid synthetic session EXPECTED FAIL

Existing clock-sync tests PASS

Existing cursor-preview tests PASS

No real participant data collected

No P0 implementation added

No P2C implementation added

No L0 implementation added

No L2C implementation added

No Fitts outcome formula frozen

No final IMU resampling frequency frozen

Tracked worktree clean

Stage 2.1 decision document committed

Stage 2.1 tag points to final qualified commit

```



Only after this gate is satisfied may development proceed to the next formal experiment-system work package.



