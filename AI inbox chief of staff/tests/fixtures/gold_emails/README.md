# Test fixtures for `workers/gold_fixture_loader.py`

These files are **synthetic** and exist solely to exercise the loader's
parse / classify / persist code paths. They are NOT representative of
production gold-eval samples.

For real evaluation, the operator drops actual `.eml` exports (e.g. from
Gmail "Show original" or `mbox` extracts) into a separate directory,
then runs:

```
python -m workers.gold_fixture_loader --dir <real-dir> --mailbox-id <uuid>
```

Anything checked into this folder is fixture data for unit tests only.
