import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, List

import simplejson as json


def convert():
    with open("1modules-summary.json", "r") as f:
        summary = json.load(f, use_decimal=True)
    with open("2modules-details.json", "r") as f:
        details = json.load(f, use_decimal=True)
    modules = {x["name"]: x for y in summary for x in y["ResultData"]["List"]}
    for module, module_data in modules.items():
        for detail in details:
            detail_data = detail["ResultData"]
            if detail_data["id"] == module_data["id"]:
                for key in detail_data:
                    if detail_data[key] is None:
                        if modules[module].get(key) is not None:
                            detail_data[key] = modules[module][key]
                detail_data["desc"] = detail_data["attributes"][-1]["desc"]
                del detail_data["acquisition"]
                modules[module].update(detail_data)
    with open("3modules-flattened.json", "w") as f:
        json.dump(modules, f, indent=4, use_decimal=True)


@dataclass
class Characterize:
    new_key: str
    regex: re.Pattern
    new_type: Callable[[str], Any]
    ok_if: Callable[[Dict], bool]


def characterize():
    skill_power_modifiers = [
        "Dimension",
        "Fusion",
        "Singular",
        "Tech",
    ]
    skill_powers = [
        "Chill",
        "Electric",
        "Fire",
        "Non-Attribute",
        "Toxic",
    ]
    patterns: List[Characterize] = []

    patterns.extend(
        [
            Characterize(
                (x.lower() + "SkillPowerModifier"),
                re.compile(x + r" Skill Power Modifier\s+(\S+?)%?\[(.)"),
                Decimal,
                lambda d: True,
            )
            for x in skill_power_modifiers
        ]
    )
    patterns.extend(
        [
            Characterize(
                x.lower() + "SkillPowerFlat",
                re.compile(x + r" Skill Power\s+\+?(-?\S+?)%?\[(.)"),
                Decimal,
                lambda d: True,
            )
            for x in skill_powers
        ]
    )
    patterns.append(
        Characterize(
            "skillDuration",
            re.compile(r"Skill Duration\s+\+?(-?\S+?)%?\[(.)"),
            Decimal,
            lambda d: True,
        )
    )
    patterns.append(
        Characterize(
            "skillCooldown",
            re.compile(r"Skill Cooldown\s+\+?(-?\S+?)%?\[(.)"),
            Decimal,
            lambda d: True,
        )
    )
    # Order is important, these come after the specific skill modifiers
    patterns.append(
        Characterize(
            "allSkillPowerModifier",
            re.compile(r"Skill Power Modifier\s+(\S+?)%?\[(.)"),
            Decimal,
            lambda d: not any("SkillPowerModifier" in x for x in d.keys()),
        ),
    )
    patterns.append(
        Characterize(
            "allSkillPowerFlat",
            re.compile(r"Skill Power\s+\+?(-?\S+?)%?\[(.)"),
            Decimal,
            lambda d: not any("SkillPowerFlat" in x for x in d.keys()),
        )
    )
    with open("3modules-flattened.json", "r") as f:
        data = json.load(f, use_decimal=True)
    for key, value in data.items():
        for pattern in patterns:
            match = re.search(pattern.regex, value["attributes"][-1]["desc"])
            if match:
                if match.group(2) == "+":
                    mode = "add"
                elif match.group(2) == "x":
                    mode = "mult"
                else:
                    raise ValueError(f"Unknown mode: {match.group(2)}")
                if not pattern.ok_if(value):
                    print(
                        f"discard {pattern.new_key} for {key}: {value["attributes"][-1]['desc']}"
                    )
                    continue
                value[pattern.new_key] = pattern.new_type(match.group(1))
                value[pattern.new_key + "Type"] = mode
    with open("4modules-with-data.json", "w") as f:
        json.dump(data, f, indent=4, use_decimal=True)


if __name__ == "__main__":
    convert()
    characterize()
