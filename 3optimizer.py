import decimal
from decimal import Decimal

import simplejson as json
from ortools.sat.python import cp_model


def find_skill_power_fields(filename="4modules-with-data.json"):
    """
    Reads a JSON file and finds all "SkillPower" key-value pairs and the 'rune_group_name' for each module.

    Args:
        filename (str): The path to the JSON file.

    Returns:
        dict: A dictionary where keys are module names and values are dictionaries
              of their "SkillPower" related key-value pairs, including 'rune_group_name'.
    """
    skill_power_data = {}
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f, use_decimal=True)

    # The data is a dictionary of modules, where each module is a dictionary.
    for module_name, module_data in data.items():
        module_skill_power = {}
        for key, value in module_data.items():
            if "SkillPower" in key:
                module_skill_power[key] = value
        if module_skill_power:
            module_skill_power["rune_group_name"] = module_data["rune_group_name"]
            skill_power_data[module_name] = module_skill_power

    return skill_power_data


class Scaled:
    """
    Scale percentages like 7.4 for 7.4% to integers, because the solver
    requires integers.
    """

    # This doesn't inherit from int because I don't want to implicitly cast to int.
    # So we implement a bunch of stuff the hard way.

    SCALE = 0

    def __init__(self, val: Decimal) -> None:
        if isinstance(val, Scaled):
            self.val = val.val
            return
        if -1 < val < 0 or 0 < val < 1:
            raise ValueError(
                "Scaled values should be input as, e.g: 7.4 for 7.4%, not .074"
            )
        # Use Decimal() here to get the precise representation and avoid floating-point errors.
        val_d = Decimal(str(val)) * Decimal(self.SCALE)
        if val_d % 1:
            raise ValueError(f"SCALE is too small, {val} * {self.SCALE} = {val_d}")
        self.val = int(val_d)

    @classmethod
    def rev(cls, val: int) -> Decimal:
        return val / cls.SCALE

    def __int__(self) -> int:
        return self.val

    def __gt__(self, other: object) -> bool:
        return not self.__le__(other)

    def __lt__(self, other: object) -> bool:
        return not self.__ge__(other)

    def __ge__(self, other: object) -> bool:
        return self.val >= other

    def __le__(self, other: object) -> bool:
        return self.val <= other

    def __pow__(self, x) -> int:
        return self.val**x

    def __mul__(self, other: object) -> object:
        if isinstance(other, type(self)):
            return self.val * other.val
        return self.val * other

    def __str__(self) -> str:
        return str(self.val)


class Pct(Scaled):
    """Percentages, represented here by a class so that they are all scaled the same."""

    # "Battle of Stamina" has a +8.79 percent, so we need to multiply by 100.
    SCALE = 100


class Time(Scaled):
    """Time in seconds, represented here by a class so that they are all scaled the same."""

    SCALE = 10


def find_optimal_build(
    max_capacity: int,
    which_flat: str = "non-attribute",
    which_modifier: str = "dimension",
    base_sp_modifier: Decimal | Pct = Decimal("68.9"),
    filename="4modules-with-data.json",
):
    """
    Finds the optimal combination of modules to maximize skill damage
    under a given capacity constraint using a constraint solver.
    - A maximum of 10 modules can be selected.
    - Only one module from each non-blank rune_group_name can be selected.
    - The final skill duration must be greater than the final skill cooldown.

    Args:
        max_capacity: The maximum total cost for the modules.
        which_flat: The primary flat skill power type to focus on.
        which_modifier: The primary modifier skill power type to focus on.
        base_sp_modifier: The skill's base skill power modifier percentage.
        filename: The path to the JSON file with module data.

    Returns:
        tuple: A tuple containing the list of selected module names and the
               maximized skill damage, or (None, None) if no solution is found.
    """
    with open(filename, "r", encoding="utf-8") as f:
        all_modules_data = json.load(f, use_decimal=True)

    base_sp_modifier = Pct(base_sp_modifier)
    module_names = list(all_modules_data.keys())
    costs = {}
    flat_sp = {}
    modifier_sp = {}
    skill_cooldowns = {}
    skill_durations = {}

    # reactor_choices_1 = {
    #    "skillAtkColossus": 2633.561,
    #    "skillCooldown": Pct(7.4),
    #    "skillDuration": Pct(10.6),
    # }
    # reactor_choices_2 = reactor_choices_1.copy()
    # reached_skill_power = 1.6
    # Fixed cooldown reductions from other sources (e.g., Arche Tuning, Reactor)
    tb_arche_tuning_cd_scaled = Pct(-5.5)
    tb_reactor_cd_scaled = Pct(-7.4)
    # tb_skill_atk_vs_colossus_scaled = Pct(54.2)

    # TODO: Optimize across the whole formula.
    # (
    #   (
    #       (
    #           (Reactor Skill Power * (Reached Skill Power + Mods/Abilites that Increase Reached Skill Power) + Atk Versus Colossus) +
    #           (Arche Tuning Skill Power * (Reached Skill Power + Mods/Abilites that Increase Reached Skill Power))
    #       ) *
    #       (1 + Base Skill Power Boost)
    #   ) * (1 + Attribute Skill Boost)
    # ) * (1 + Type Skill Boost) = Skill Power

    for name, data in all_modules_data.items():
        # Use the cost from the last attribute level
        costs[name] = data.get("attributes", [{}])[-1].get("cost", 99)

        flat_key = f"{which_flat}SkillPowerFlat"
        all_flat_key = "allSkillPowerFlat"
        current_flat_sp = data.get(flat_key, 0) + data.get(all_flat_key, 0)
        flat_sp[name] = Pct(current_flat_sp)

        modifier_key = f"{which_modifier}SkillPowerModifier"
        all_modifier_key = "allSkillPowerModifier"
        current_modifier_sp = data.get(modifier_key, 0) + data.get(all_modifier_key, 0)
        modifier_sp[name] = Pct(current_modifier_sp)

        skill_cooldowns[name] = Pct(data.get("skillCooldown", 0))
        skill_durations[name] = Pct(data.get("skillDuration", 0))

    # --- Create the model ---
    model = cp_model.CpModel()

    # --- Create variables ---
    selected = {name: model.NewBoolVar(f"sel_{name}") for name in module_names}

    # --- Define constraints ---
    # 1. Total cost must not exceed max_capacity.
    model.Add(
        sum(selected[name] * costs[name] for name in module_names) <= max_capacity
    )

    # 2. No more than this many modules can be selected.
    model.Add(sum(selected.values()) <= 10)

    # 3. No more than one module for each non-blank rune_group_name.
    rune_groups = {}
    for name, data in all_modules_data.items():
        group_name = data.get("rune_group_name")
        if group_name:  # Filters out None or ""
            rune_groups.setdefault(group_name, []).append(name)

    for group_name, modules_in_group in rune_groups.items():
        model.Add(sum(selected[module_name] for module_name in modules_in_group) <= 1)

    # 4. The final skill duration must be greater than the final skill cooldown.

    total_cooldown_var = model.NewIntVar(Pct(-1000), Pct(1000), "total_cooldown")
    model.Add(
        total_cooldown_var
        == sum(selected[name] * skill_cooldowns[name] for name in module_names)
        + tb_arche_tuning_cd_scaled
        + tb_reactor_cd_scaled
    )
    total_duration_var = model.NewIntVar(Pct(-1000), Pct(1000), "total_duration")
    model.Add(
        total_duration_var
        == sum(selected[name] * skill_durations[name] for name in module_names)
    )

    # Base values for the character's skill
    base_duration_s = Time(5)
    base_cooldown_s = Time(40 - 0.3)  # Within 0.3s is the same server tick.

    model.Add(
        base_duration_s * (Pct(100) + total_duration_var)
        >= base_cooldown_s * (Pct(100) + total_cooldown_var)
    )

    # --- Define the objective function ---
    # We want to maximize (1 + total_flat_sp) * (1 + base_sp_modifier + total_modifier_sp)

    # Create integer variables for the total skill powers.
    total_flat_sp_var = model.NewIntVar(Pct(-1000), Pct(1000), "total_flat_sp")
    model.Add(
        total_flat_sp_var
        == sum(selected[name] * flat_sp[name] for name in module_names)
    )

    total_modifier_sp_var = model.NewIntVar(Pct(-1000), Pct(1000), "total_modifier_sp")
    model.Add(
        total_modifier_sp_var
        == sum(selected[name] * modifier_sp[name] for name in module_names)
        + base_sp_modifier
    )

    # Create the objective variable (the product of the two terms, skill_power_modifier * skill_power_value).
    objective_var = model.NewIntVar(0, (Pct(1000) * Pct(1000)) * 2, "objective")
    model.AddMultiplicationEquality(
        objective_var, [total_flat_sp_var, total_modifier_sp_var]
    )

    model.Maximize(objective_var)

    # --- Solve the model ---
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    print(solver.Values([total_modifier_sp_var, total_flat_sp_var, objective_var]))

    # --- Extract and return the results ---
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        optimal_modules = {
            name: all_modules_data[name]
            for name, var in selected.items()
            if solver.Value(var)
        }
        return optimal_modules

    return None, None


if __name__ == "__main__":
    c = decimal.getcontext()
    c.traps[decimal.FloatOperation] = True

    # Define your constraints
    MAX_MODULE_CAPACITY = (
        85 - 6
    ) * 2  # Max is 85, minus 6 for transcendent, times two because all costs are halved
    CHARACTER_BASE_MODIFIER = Decimal("68.9")
    FLAT_SKILL_TYPE = "non-attribute"
    MODIFIER_SKILL_TYPE = "dimension"

    print(f"Finding optimal build with max capacity: {MAX_MODULE_CAPACITY}...")

    optimal_set = find_optimal_build(
        max_capacity=MAX_MODULE_CAPACITY,
        which_flat=FLAT_SKILL_TYPE,
        which_modifier=MODIFIER_SKILL_TYPE,
        base_sp_modifier=Pct(CHARACTER_BASE_MODIFIER),
    )

    if optimal_set:
        print("\nOptimal build found")
        total_cooldown = sum(
            module.get("skillCooldown", 0) for module in optimal_set.values()
        )
        print(f"Total Skill Cooldown: {total_cooldown:.2f}%")
        total_duration = sum(
            module.get("skillDuration", 0) for module in optimal_set.values()
        )
        print(f"Total Skill Duration: {total_duration:.2f}%")
        print(f"Selected Modules ({len(optimal_set)}):")
        for module in sorted(optimal_set.keys()):
            which = ""
            try:
                which = [
                    x
                    for x in optimal_set[module].keys()
                    if "SkillPower" in x and "Type" not in x
                ][0]
            except IndexError:
                pass
            print(
                f"- {module:30s} {optimal_set[module]['rune_group_name']:12s} {which:30s} pow {optimal_set[module].get(which, 0):>6.2f} cd {optimal_set[module].get('skillCooldown', 0):>6.2f} dur {optimal_set[module].get('skillDuration', 0):>6.2f}"
            )

    else:
        print("No optimal solution found for the given constraints.")
