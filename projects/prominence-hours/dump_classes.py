import json
import os
import re
import subprocess

inventory_path = "/home/<USERNAME_REDACTED>/prominence-hours/jar_inventory.json"
out_root = "/home/<USERNAME_REDACTED>/prominence-hours/javap"
with open(inventory_path) as f:
    inventory = json.load(f)

os.makedirs(out_root, exist_ok=True)
index = []
for family, records in inventory.items():
    family_dir = os.path.join(out_root, re.sub(r"[^A-Za-z0-9_.-]+", "_", family))
    os.makedirs(family_dir, exist_ok=True)
    for record in records:
        jar = record["path"]
        selected = set()
        for hit in record["token_hits"]:
            tokens = set(hit["tokens"])
            cls = hit["class"]
            if tokens.intersection({"DamageSource", "damageSources", "getOwner", "setOwner", "getAttacker", "getEntity", "owner", "caster"}):
                selected.add(cls)
        # Add classes whose names identify likely damage/ownership paths even if the byte-token scan missed them.
        for cls in record["candidate_classes"]:
            if any(term in cls.lower() for term in ("projectile", "damage", "customspell", "spellhelper", "ability", "effect")):
                selected.add(cls)
        for cls in sorted(selected):
            proc = subprocess.run(
                ["javap", "-classpath", jar, "-p", "-c", "-s", cls],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            path = os.path.join(family_dir, cls + ".txt")
            with open(path, "w") as f:
                f.write(proc.stdout)
            index.append({"family": family, "jar": jar, "class": cls, "path": path, "exit": proc.returncode})

with open(os.path.join(out_root, "index.json"), "w") as f:
    json.dump(index, f, indent=2)
print(f"dumped {len(index)} classes; failures={sum(row['exit'] != 0 for row in index)}")
