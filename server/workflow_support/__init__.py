"""Share the editable public WORKFLOW modules with the private model gateway."""
from pathlib import Path

# Public net/business/self_check live in the question materials; gateway remains
# here. Both sides import the same modules, with no generated source copies.
__path__.insert(0, str(Path(__file__).resolve().parents[2] /
                      'candidate/tasks/WORKFLOW/devtools/workflow_support'))
