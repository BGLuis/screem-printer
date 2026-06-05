import questionary
from prompt_toolkit.styles import Style

s = Style([
    ("test1", "fg:blue"),
    ("test2", "bg:blue"),
    ("test3", "ansiblue"),
    ("test4", "#0000ff"),
])
for rule in s.style_rules:
    print(rule)
