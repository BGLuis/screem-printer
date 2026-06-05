import questionary
import questionary.prompts.common

questionary.prompts.common.INDICATOR_SELECTED = "[x]"
questionary.prompts.common.INDICATOR_UNSELECTED = "[ ]"

custom_style = questionary.Style([
    ("selected", "fg:blue"),
])

print(questionary.checkbox(
    "Test",
    choices=["A", "B"],
    style=custom_style
).ask())
