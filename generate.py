import json
import math
from pathlib import Path

# v REPLACE PLACEHOLDERS v
DATAPACK_NAMESPACE = "foo"
DESTINATION_FOLDER_PATH = Path("") # Note: Use '/' to separate folders, not '\'
BLOCK_STATE_PROPERTIES_PATH = Path("")
BLOCK_VALUE_CLASSES_PATH = Path("")
# ^ REPLACE PLACEHOLDERS ^

BLOCK_TAGS_FOLDER_PATH = DESTINATION_FOLDER_PATH / DATAPACK_NAMESPACE / "tags/block"
NUMBER_PROVIDERS_FOLDER_PATH = DESTINATION_FOLDER_PATH / DATAPACK_NAMESPACE / "context_int_provider"


def get_block_value_data():
    with BLOCK_VALUE_CLASSES_PATH.open("r") as f:
        data = json.load(f)
    return data

def get_block_property_data():
    with BLOCK_STATE_PROPERTIES_PATH.open("r") as f:
        data = json.load(f)
    return data


def gen_block_id_tags(bit_count, blocks):
    block_tags_data = [{"values": []} for _ in range(bit_count)] # Using EMPTY_BLOCK_TAG_CONTENT instead of {...} makes them all share a reference, so don't do that

    # Fill block tag data
    for i, block_id in enumerate(blocks):
        bits = [(i >> bit) & 1 for bit in range(bit_count - 1, -1, -1)] # Create a list of bits that represent i, taken from stackoverflow
        for j, bit in enumerate(bits):
            if bit == 1:
                block_tags_data[j]["values"].append(block_id)

    # Write data to block tags
    folder_path = BLOCK_TAGS_FOLDER_PATH / "block_id"
    folder_path.mkdir(parents=True, exist_ok=True)

    for i in range(bit_count):
        file_path = folder_path / f"b{i}.json"
        with file_path.open("w") as f:
            json.dump(block_tags_data[i], f, separators=(',', ':'))


def gen_block_id_provider(bit_count):
    number_provider_data = {"type":"minecraft:add","inputs":[]}
    for i in range(bit_count):
        number_provider_data["inputs"].append({"type":"minecraft:conditional","condition":{"type":"minecraft:match_block","blocks":f"#{DATAPACK_NAMESPACE}:block_id/b{i}"},"on_true":2**i})

    file_path = NUMBER_PROVIDERS_FOLDER_PATH / "block_id.json"
    with file_path.open("w") as f:
        json.dump(number_provider_data, f, separators=(',', ':'))


def get_block_state_groups(block_value_data): # A group consists of blocks that share the same possible block states across all properties.
    groups = {} # {(tuple containing all properties with value class & possible values):[all blocks that match]}
    for block, block_data in block_value_data.items():
        key = tuple(
            (property, value_data["value_class"], tuple(value_data["values"]))
            for property, value_data in sorted(block_data.items()) # Should already be pre-sorted from the datagen, but just in case
        )

        if not key in groups:
            groups[key] = set()

        if not block in groups[key]:
            groups[key].add(block)

    for key in groups:
        groups[key] = sorted(groups[key]) # Sorted already converts to a list, no list() necessary

    return groups


def gen_block_state_group_tags(groups):
    folder_path = BLOCK_TAGS_FOLDER_PATH / "groups"
    folder_path.mkdir(parents=True, exist_ok=True)

    for i, blocks in enumerate(groups.values()):
        block_tag_data = {"values": blocks}

        file_path = folder_path / f"{i}.json"
        with file_path.open("w") as f:
            json.dump(block_tag_data, f, separators=(',', ':'))



def get_value_class_branches(groups): # Different branches of the same value class have different possible values, but pull from the same value pool.
    branches = {} # {"age":{<value class>:{<tuple of possible values>:[<indices of groups in that branch>]}}, ...}
    for i, block_state_data in enumerate(groups):
        for property, value_class, values in block_state_data:
            if not property in branches:
                branches[property] = {}

            if not value_class in branches[property]:
                branches[property][value_class] = {}

            if not values in branches[property][value_class]:
                branches[property][value_class][values] = []

            branches[property][value_class][values].append(i)
    return branches


def gen_value_class_tags(branches): # Block tag for each group within the value class, and a combined one for the total value class
    for property, value_classes in branches.items():
        for value_class_index, branches_data in value_classes.items():
            folder_path = BLOCK_TAGS_FOLDER_PATH / "value_classes" / property / str(value_class_index)
            folder_path.mkdir(parents=True, exist_ok=True)

            value_class_block_tag_data = {"values": []}

            for branch_index, groups in enumerate(branches_data.values()):
                value_class_block_tag_data["values"].append(f"#{DATAPACK_NAMESPACE}:value_classes/{property}/{value_class_index}/branch_{branch_index}")
                branch_block_tag_data = {"values": [f"#{DATAPACK_NAMESPACE}:groups/{group}" for group in groups]}

                file_path = folder_path / f"branch_{branch_index}.json"
                with file_path.open("w") as f:
                    json.dump(branch_block_tag_data, f, separators=(',', ':'))

            file_path = folder_path / "all.json"
            with file_path.open("w") as f:
                json.dump(value_class_block_tag_data, f, separators=(',', ':'))


def gen_individual_block_state_providers(block_property_data, branches, groups): # TODO: Add binary search to get the value class & branch (Benchmark at which point it's worth it, because number provider complexity grows and the block tags get larger too). Add new block tags, or use "OR" in the checks? Also, clean up this function.
    # Layer 1: Run the correct value class. Layer 2: Run the correct branch.
    folder_path = NUMBER_PROVIDERS_FOLDER_PATH / "block_state"
    folder_path.mkdir(parents=True, exist_ok=True)

    blocks_per_group = list(groups.values())

    for property, value_classes in branches.items():
        nof_value_classes = len(value_classes)

        if nof_value_classes == 1:
            layer_1_provider_data = {"type":"minecraft:conditional","condition":{"type":"minecraft:match_block","blocks":f"#{DATAPACK_NAMESPACE}:value_classes/{property}/0/all"},"on_true":{},"on_false":-1}
        else:
            layer_1_provider_data = {"type":"minecraft:number_dispatcher","cases":[],"default":-1}

        for value_class_index, branches_data in value_classes.items():
            nof_branches = len(branches_data)

            groups_of_value_class = list(branches_data.values())
            nof_blocks_per_branch = [sum([len(blocks_per_group[group]) for group in groups_of_value_class[branch_index]]) for branch_index in range(nof_branches)] # TODO: Double-check if the ordering is correct (Correct group, correct branch etc)
            biggest_branch_index = nof_blocks_per_branch.index(max(nof_blocks_per_branch)) # First occurrence if multiple branches have the same number of blocks

            if nof_branches == 1:
                layer_2_provider_data = f"{DATAPACK_NAMESPACE}:zprivate/block_state/{property}/{value_class_index}/branch_0"
            elif nof_branches == 2:
                smaller_branch_index = 1 if biggest_branch_index == 0 else 0
                layer_2_provider_data = {"type":"minecraft:conditional","condition":{"type":"minecraft:match_block","blocks":f"#{DATAPACK_NAMESPACE}:value_classes/{property}/0/branch_{smaller_branch_index}"},"on_true":f"{DATAPACK_NAMESPACE}:zprivate/block_state/{property}/{value_class_index}/branch_{smaller_branch_index}","on_false":f"{DATAPACK_NAMESPACE}:zprivate/block_state/{property}/{value_class_index}/branch_{biggest_branch_index}"}
            else:
                layer_2_provider_data = {"type":"minecraft:number_dispatcher","cases":[],"default":f"{DATAPACK_NAMESPACE}:zprivate/block_state/{property}/{value_class_index}/branch_{biggest_branch_index}"}
                for branch_index in range(len(branches_data)):
                    if branch_index == biggest_branch_index:
                        continue
                    layer_2_case = {"condition":{"type":"minecraft:match_block","blocks":f"#{DATAPACK_NAMESPACE}:value_classes/{property}/{value_class_index}/branch_{branch_index}"},"value":f"{DATAPACK_NAMESPACE}:zprivate/block_state/{property}/{value_class_index}/branch_{branch_index}"}
                    layer_2_provider_data["cases"].append(layer_2_case)

            # Fill layer 1
            if nof_value_classes == 1:
                layer_1_provider_data["on_true"] = layer_2_provider_data
            else:
                layer_1_case = {"condition":{"type":"minecraft:match_block","blocks":f"#{DATAPACK_NAMESPACE}:value_classes/{property}/{value_class_index}/all"},"value":layer_2_provider_data}
                layer_1_provider_data["cases"].append(layer_1_case)

            # Write file
            file_path = folder_path / f"{property}.json"
            with file_path.open("w") as f:
                json.dump(layer_1_provider_data, f, separators=(',', ':'))

    # Make internal branch-specific number providers (that were referenced earlier in this function)
    for property, value_classes in block_property_data.items():
        value_offset = 0
        for value_class_index in range(len(value_classes)):
            branches_data = branches[property][value_class_index]
            possible_values = value_classes[value_class_index]
            possible_value_indices_per_branch = list(branches[property][value_class_index].keys())
            for branch_index in range(len(branches_data)):
                branch_value_indices = possible_value_indices_per_branch[branch_index]
                number_provider_data = get_individual_block_state_provider_body(property, possible_values, branch_value_indices, value_offset)

                # Write file
                folder_path = NUMBER_PROVIDERS_FOLDER_PATH / "zprivate" / "block_state" / property / str(value_class_index)
                folder_path.mkdir(parents=True, exist_ok=True)
                file_path = folder_path / f"branch_{branch_index}.json"
                with file_path.open("w") as f:
                    json.dump(number_provider_data, f, separators=(',', ':'))

            value_offset += len(value_classes[value_class_index - 1])
            # TODO: Maybe make the public number providers run pure "number dispatcher" without binary search or branch distinction, if that's faster if I don't already know the branch? Would need to depend on the property (smth like 'age' would benefit from binary search anyway, but then again, it has 8 branches). I could also experiment with merging the binary search for value classes & branches into a single binary search.
            # => Make sure it's not slower than running a naïve number dispatcher without any grouping logic or binary search


def get_individual_block_state_provider_body(property, all_value_class_states, branch_state_indices, value_offset):
    # Map branch state indices to state values
    all_branch_values = [all_value_class_states[i] for i in branch_state_indices]

    # Base cases
    if len(all_branch_values) == 1:
        return branch_state_indices[0] + value_offset

    if len(all_branch_values) == 2:
        return {"type":"minecraft:conditional","condition":{"type":"minecraft:match_block","state":{f"{property}":f"{all_branch_values[0]}"}},"on_true":branch_state_indices[0] + value_offset,"on_false":branch_state_indices[1] + value_offset}

    if len(all_branch_values) == 3:
        return {"type":"minecraft:number_dispatcher","cases":[{"condition":{"type":"minecraft:match_block","state":{f"{property}":f"{all_branch_values[0]}"}},"value":branch_state_indices[0] + value_offset},{"condition":{"type":"minecraft:match_block","state":{f"{property}":f"{all_branch_values[1]}"}},"value":branch_state_indices[1] + value_offset}],"default":branch_state_indices[2] + value_offset}

    if len(all_branch_values) == 4: # I benchmarked, and this is still faster than binary search (TODO: Benchmark if this is the point where it flips)
        return {"type":"minecraft:number_dispatcher","cases":[{"condition":{"type":"minecraft:match_block","state":{f"{property}":f"{all_branch_values[0]}"}},"value":branch_state_indices[0] + value_offset},{"condition":{"type":"minecraft:match_block","state":{f"{property}":f"{all_branch_values[1]}"}},"value":branch_state_indices[1] + value_offset},{"condition":{"type":"minecraft:match_block","state":{f"{property}":f"{all_branch_values[2]}"}},"value":branch_state_indices[2] + value_offset}],"default":branch_state_indices[3] + value_offset}

    # Recursive case (Binary search)
    max_index = len(branch_state_indices) // 2
    max_value = branch_state_indices[max_index]
    body = {"type":"minecraft:conditional","condition":{"type":"minecraft:match_block","state":{f"{property}":{"max":f"{max_value}"}}},"on_true":{},"on_false":{}}
    first_half = branch_state_indices[:max_index + 1] # [..., max_index]
    second_half = branch_state_indices[max_index + 1:] # (max_index, ...]
    body["on_true"] = get_individual_block_state_provider_body(property, all_value_class_states, first_half, value_offset)
    body["on_false"] = get_individual_block_state_provider_body(property, all_value_class_states, second_half, value_offset)
    return body

# Logic:
# - Inside a value class, name the block tags for "value range" 'branch'
# - In the publicly available individual block state providers, first check the value class in a number dispatcher, and make it run another provider that checks the branch. OR FLATTEN THE TWO CHECKS INTO A SINGLE "block state branch" CHECK? -> Don't flatten, because multiple block state branches could have the same values for this particular block state. That provider (inlined) calls the internal per-branch provider that uses binary search (basically the provider body).
# - In the "get_block_state" (merged) provider, check the block state branch at the very top (default to <none>), maybe binary search it if there are a lot of branches. Then inside, run the individual block state providers (the internal ones: At build-time, I already know which branch & value classes I'm on) and combine the results. Smallest to largest, or largest to smallest? Doesn't matter, I just need to be consistent. It's called "mixed-radix"
# - I can re-use the same "get_block_state (merged)" provider for the "single int for whole block id + blockstate" and for "int for blockid, int for blockstate". I just need to add a different prefix at the end

# Run
NUMBER_PROVIDERS_FOLDER_PATH.mkdir(parents=True, exist_ok=True)

block_value_data = get_block_value_data()
blocks = list(block_value_data.keys())
bit_count = math.ceil(math.log2(len(blocks)))
gen_block_id_tags(bit_count, blocks)
gen_block_id_provider(bit_count)

groups = get_block_state_groups(block_value_data)
gen_block_state_group_tags(groups)

branches = get_value_class_branches(groups)
gen_value_class_tags(branches)

block_property_data = get_block_property_data()
gen_individual_block_state_providers(block_property_data, branches, groups)
