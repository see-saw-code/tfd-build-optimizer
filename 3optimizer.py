import json
from ortools.sat.python import cp_model


def optimize_me(
    which_flat="non-attribute", which_modifier="dimension", base_sp_modifier=0.69
):
    # (
    #   (
    #       (
    #           (
    #               (Reactor Skill Power + Arche Tuning Skill Power) * (Reached Skill Power + Mods that Increase Reached Skill Power)
    #           )
    #       * (1 + Base Skill Power Boost Ratio)
    #   ) * (1 + Attribute Skill Boost Ratio)
    # ) * (1 + Type Skill Boost Ratio))
    # TODO: Manage reactor skill boosts and arche tuning skill boosts and bonus atk vs colossi
    reactor_skill_power = 1
    arche_tuning_skill_power = 1
    reached_skill_power = 1
    base_skill_power_boost_ratio = 1
    attribute_skill_boost_ratio = 1
    type_skill_boost_ratio = 1

    which_sp_flat = {
        "chill": 0,
        "electric": 0,
        "fire": 0,
        "non-attribute": 0,
        "toxic": 0,
        "all": 0,
    }
    skill_power = which_sp_flat[which_flat] + which_sp_flat["all"]

    which_sp_modifier = {
        "dimension": 0,
        "fusion": 0,
        "singular": 0,
        "tech": 0,
        "all": 0,
    }
    skill_power_modifier = (
        which_sp_modifier[which_modifier] + which_sp_modifier["all"] + base_sp_modifier
    )

    skill_damage = (1 + skill_power) * (1 + skill_power_modifier)

    return skill_damage


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
        data = json.load(f)

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


def find_optimal_build(
    max_capacity: int,
    which_flat: str = "non-attribute",
    which_modifier: str = "dimension",
    base_sp_modifier: float = 0.69,
    filename="4modules-with-data.json.json",
):
    """
    Finds the optimal combination of modules to maximize skill damage
    under a given capacity constraint using a constraint solver.
    - A maximum of 10 modules can be selected.
    - Only one module from each non-blank rune_group_name can be selected.
    - The final skill duration must be greater than the final skill cooldown.

    Args:
        max_capacity (int): The maximum total cost for the modules.
        which_flat (str): The primary flat skill power type to focus on.
        which_modifier (str): The primary modifier skill power type to focus on.
        base_sp_modifier (float): The character's base skill power modifier.
        filename (str): The path to the JSON file with module data.

    Returns:
        tuple: A tuple containing the list of selected module names and the
               maximized skill damage, or (None, None) if no solution is found.
    """
    with open(filename, "r", encoding="utf-8") as f:
        all_modules_data = json.load(f)

    module_names = list(all_modules_data.keys())
    costs = {}
    flat_sp = {}
    modifier_sp = {}
    skill_cooldowns = {}
    skill_durations = {}

    # Use a scaling factor to work with integers, as the solver prefers them.
    # We use 1000 to preserve one decimal place of precision (e.g., 7.5%)
    SCALE = 1000

    for name, data in all_modules_data.items():
        # Use the cost from the last attribute level
        costs[name] = data.get("attributes", [{}])[-1].get("cost", 99)

        flat_key = f"{which_flat}SkillPowerFlat"
        all_flat_key = "allSkillPowerFlat"
        current_flat_sp = data.get(flat_key, 0.0) + data.get(all_flat_key, 0.0)
        flat_sp[name] = int(
            current_flat_sp * SCALE / 100
        )  # Convert percentage to float

        modifier_key = f"{which_modifier}SkillPowerModifier"
        all_modifier_key = "allSkillPowerModifier"
        current_modifier_sp = data.get(modifier_key, 0.0) + data.get(
            all_modifier_key, 0.0
        )
        modifier_sp[name] = int(current_modifier_sp * SCALE / 100)

        skill_cooldowns[name] = int(data.get("skillCooldown", 0.0) * SCALE / 100)
        skill_durations[name] = int(data.get("skillDuration", 0.0) * SCALE / 100)

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
    model.Add(sum(selected.values()) <= 9)

    # 3. No more than one module for each non-blank rune_group_name.
    rune_groups = {}
    for name, data in all_modules_data.items():
        group_name = data.get("rune_group_name")
        if group_name:  # Filters out None or ""
            rune_groups.setdefault(group_name, []).append(name)

    for group_name, modules_in_group in rune_groups.items():
        model.Add(sum(selected[module_name] for module_name in modules_in_group) <= 1)

    # 4. The final skill duration must be greater than the final skill cooldown.

    # Fixed cooldown reductions from other sources (e.g., Arche Tuning, Reactor)
    arche_tuning_cd_scaled = int(-5.5 * SCALE / 100)
    reactor_cd_scaled = int(-7.4 * SCALE / 100)

    total_cooldown_var = model.NewIntVar(-1000 * SCALE, 1000 * SCALE, "total_cooldown")
    model.Add(
        total_cooldown_var
        == sum(selected[name] * skill_cooldowns[name] for name in module_names)
        + arche_tuning_cd_scaled
        + reactor_cd_scaled
    )
    total_duration_var = model.NewIntVar(-1000 * SCALE, 1000 * SCALE, "total_duration")
    model.Add(
        total_duration_var
        == sum(selected[name] * skill_durations[name] for name in module_names)
    )

    # Base values for the character's skill
    base_duration_s = 5
    base_cooldown_s = 40

    model.Add(
        base_duration_s * (SCALE + total_duration_var)
        > base_cooldown_s * (SCALE + total_cooldown_var)
    )

    # --- Define the objective function ---
    # We want to maximize (1 + total_flat_sp) * (1 + base_sp_modifier + total_modifier_sp)

    # Create integer variables for the total skill powers.
    total_flat_sp_var = model.NewIntVar(-1000 * SCALE, 1000 * SCALE, "total_flat_sp")
    model.Add(
        total_flat_sp_var
        == sum(selected[name] * flat_sp[name] for name in module_names)
    )

    total_modifier_sp_var = model.NewIntVar(
        -1000 * SCALE, 1000 * SCALE, "total_modifier_sp"
    )
    model.Add(
        total_modifier_sp_var
        == sum(selected[name] * modifier_sp[name] for name in module_names)
    )

    # Create variables for the two terms of the product, scaled up.
    term1 = model.NewIntVar(0, 2000 * SCALE, "term1")
    model.Add(term1 == (1 * SCALE) + total_flat_sp_var)

    base_sp_modifier_int = int(base_sp_modifier * SCALE)
    term2 = model.NewIntVar(0, 2000 * SCALE, "term2")
    model.Add(term2 == (1 * SCALE) + base_sp_modifier_int + total_modifier_sp_var)

    # Create the objective variable (the product of the two terms).
    objective_var = model.NewIntVar(0, 4000 * SCALE * SCALE, "objective")
    model.AddMultiplicationEquality(objective_var, [term1, term2])

    model.Maximize(objective_var)

    # --- Solve the model ---
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    # --- Extract and return the results ---
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        optimal_modules = {
            name: all_modules_data[name]
            for name, var in selected.items()
            if solver.Value(var)
        }
        max_damage = solver.ObjectiveValue() / (SCALE * SCALE)
        return optimal_modules, max_damage

    return None, None


if __name__ == "__main__":
    # Define your constraints
    MAX_MODULE_CAPACITY = (
        85 - 6
    ) * 2  # Max is 85, minus 6 for transcendent, times two because all costs are halved
    CHARACTER_BASE_MODIFIER = 0.69
    FLAT_SKILL_TYPE = "non-attribute"
    MODIFIER_SKILL_TYPE = "dimension"

    print(f"Finding optimal build with max capacity: {MAX_MODULE_CAPACITY}...")

    optimal_set, max_damage = find_optimal_build(
        max_capacity=MAX_MODULE_CAPACITY,
        which_flat=FLAT_SKILL_TYPE,
        which_modifier=MODIFIER_SKILL_TYPE,
        base_sp_modifier=CHARACTER_BASE_MODIFIER,
    )

    if optimal_set:
        print(
            f"\nOptimal build found with estimated damage multiplier: {max_damage:.2f}"
        )
        total_cooldown = sum(
            module.get("skillCooldown", 0.0) for module in optimal_set.values()
        )
        print(f"Total Skill Cooldown: {total_cooldown:.2f}%")
        total_duration = sum(
            module.get("skillDuration", 0.0) for module in optimal_set.values()
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
                f"- {module:30s} {optimal_set[module]['rune_group_name']:15s} {which:30s} pow {optimal_set[module].get(which, 0):>6.2f} cd {optimal_set[module].get('skillCooldown', 0):>6.2f} dur {optimal_set[module].get('skillDuration', 0):>6.2f}"
            )

    else:
        print("No optimal solution found for the given constraints.")
