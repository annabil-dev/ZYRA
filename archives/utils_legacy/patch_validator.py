from pathlib import Path
import shutil
p=Path(r'D:\Semester 5\AI\my_ai\ai\blockchain\pouw_validator.py')
shutil.copy2(p, str(p)+'.bak')
s=p.read_text(encoding='utf-8')
old='return False, f"Unittest failed. Tests did not pass."'
new='return False, {"status": "FAILED", "reason": "Unittest failed. Tests did not pass.", "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:], "retry": True}'
assert old in s
p.write_text(s.replace(old,new), encoding='utf-8')
print('patched')
