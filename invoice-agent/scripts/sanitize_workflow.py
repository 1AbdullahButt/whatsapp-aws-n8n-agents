"""Clean a workflow exported from n8n before it is saved in the repo.

    .venv\\Scripts\\python scripts\\sanitize_workflow.py exported.json n8n\\workflows\\invoice_intake.json

Keeps only what is needed to import the workflow again: id, name, nodes,
connections, settings (and active=false). Drops meta.instanceId, pinData,
version ids, sharing/project info, tags and timestamps. Removes any
"credentials" entry from nodes, then refuses to write if the word
"credentials" or "instanceId" is still anywhere in the file.
"""
import json
import sys
from pathlib import Path

KEEP_TOP_LEVEL = ("id", "name", "nodes", "connections", "settings")
NODE_KEYS_TO_DROP = ("credentials",)


def sanitize(workflow):
    # `n8n export:workflow` writes a list, even for one workflow.
    if isinstance(workflow, list):
        if len(workflow) != 1:
            raise ValueError(f"expected 1 workflow, got {len(workflow)}")
        workflow = workflow[0]
    clean = {key: workflow[key] for key in KEEP_TOP_LEVEL if key in workflow}
    clean["active"] = False
    for node in clean["nodes"]:
        for key in NODE_KEYS_TO_DROP:
            node.pop(key, None)
    return clean


def check_clean(text):
    for word in ("credentials", "instanceId", "pinData"):
        if word in text:
            raise ValueError(f"'{word}' still present, not saving")


def main(source, target):
    workflow = json.loads(Path(source).read_text(encoding="utf-8"))
    text = json.dumps(sanitize(workflow), indent=2, ensure_ascii=False) + "\n"
    check_clean(text)
    Path(target).write_text(text, encoding="utf-8")
    print(f"saved {target}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
