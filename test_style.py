import questionary
import questionary.prompts.common

questionary.prompts.common.INDICATOR_SELECTED = "[x]"
questionary.prompts.common.INDICATOR_UNSELECTED = "[ ]"

print(questionary.Style([
    ("selected", "fg:blue"),
]).style_rules)
