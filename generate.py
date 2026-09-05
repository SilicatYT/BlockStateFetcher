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
        for value_class_index, branches in value_classes.items():
            folder_path = BLOCK_TAGS_FOLDER_PATH / "value_classes" / property / str(value_class_index)
            folder_path.mkdir(parents=True, exist_ok=True)

            value_class_block_tag_data = {"values": []}

            for branch_index, groups in enumerate(branches.values()):
                value_class_block_tag_data["values"].append(f"{DATAPACK_NAMESPACE}:value_classes/{property}/{value_class_index}/branch_{branch_index}.json")
                branch_block_tag_data = {"values": [f"#{DATAPACK_NAMESPACE}:groups/{group}" for group in groups]}

                file_path = folder_path / f"branch_{branch_index}.json"
                with file_path.open("w") as f:
                    json.dump(branch_block_tag_data, f, separators=(',', ':'))

            file_path = folder_path / "all.json"
            with file_path.open("w") as f:
                json.dump(value_class_block_tag_data, f, separators=(',', ':'))


def gen_individual_block_state_providers(block_property_data): # TODO: Rework so it distinguishes between the branches
    for property, value_classes in block_property_data.items():
        if len(value_classes) == 1:
            number_provider_data = get_individual_block_state_provider_body(property, value_classes[0], 0)

        elif len(value_classes) == 2:
            number_provider_data = {"type":"minecraft:conditional","condition":{"type":"minecraft:match_block","blocks":f"#{DATAPACK_NAMESPACE}:value_class/{property}/1"},"on_true":{},"on_false":{}}
            number_provider_data["on_true"] = get_individual_block_state_provider_body(property, value_classes[1], len(value_classes[0]))
            number_provider_data["on_false"] = get_individual_block_state_provider_body(property, value_classes[0], 0)

        else:
            number_provider_data = {"type":"minecraft:number_dispatcher","cases":[],"default":{}}
            number_provider_data["default"] = get_individual_block_state_provider_body(property, value_classes[0], 0)
            value_offset = 0

            for i in range(1, len(value_classes)):
                value_offset += len(value_classes[i - 1])
                new_case = {"condition":{"type":"minecraft:match_block","blocks":f"#{DATAPACK_NAMESPACE}:value_class/{property}/{i}"},"value":{}}
                new_case["value"] = get_individual_block_state_provider_body(property, value_classes[i], value_offset)
                number_provider_data["cases"].append(new_case)

        folder_path = NUMBER_PROVIDERS_FOLDER_PATH / "block_state"
        folder_path.mkdir(parents=True, exist_ok=True)
        file_path = folder_path / f"{property}.json"
        with file_path.open("w") as f:
            json.dump(number_provider_data, f, separators=(',', ':'))


def get_individual_block_state_provider_body(property, possible_states, value_offset): # TODO: Rework so it distinguishes between the branches
    # Base cases
    if len(possible_states) == 1:
        return value_offset

    if len(possible_states) == 2:
        return {"type":"minecraft:conditional","condition":{"type":"minecraft:match_block","state":{f"{property}":f"{possible_states[0]}"}},"on_true":value_offset,"on_false":value_offset+1}

    if len(possible_states) == 3:
        return {"type":"minecraft:number_dispatcher","cases":[{"condition":{"type":"minecraft:match_block","state":{f"{property}":f"{possible_states[0]}"}},"value":value_offset},{"condition":{"type":"minecraft:match_block","state":{f"{property}":f"{possible_states[1]}"}},"value":value_offset+1}],"default":value_offset+2}

    # Recursive case (Binary search)
    max_index = len(possible_states) // 2
    max_value = possible_states[max_index]
    body = {"type":"minecraft:conditional","condition":{"type":"minecraft:match_block","state":{f"{property}":{"max":f"{max_value}"}}},"on_true":{},"on_false":{}}
    first_half = possible_states[:max_index + 1] # [..., max_index]
    second_half = possible_states[max_index + 1:] # (max_index, ...]
    body["on_true"] = get_individual_block_state_provider_body(property, first_half, value_offset)
    body["on_false"] = get_individual_block_state_provider_body(property, second_half, value_offset + max_index + 1)
    return body

# TODO: Fix the oversight where if a block state isn't present, the returned value is 0 instead of -1 (I didn't add a case for "default" at the bottom level in get_individual_block_state_provider_body. Maybe I can add it somewhere else though? Perhaps a block tag check at the top for "does this block even have this property?" Or a "min:0" at the very top?)
# TODO: There's an MC bug that fails the "max" check if it's outside the current block's cap. Either wait until that bug is fixed, or add block tag checks, or don't do binary search. Or split the ages into different value classes too? Does this affect other block state properties as well?
#       => Provide number providers that check for the value range block tag at the top (default: -1) that run special internal number providers that only work with the specific range. "Get all blockstates" for any block would directly run those internal ones

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
gen_individual_block_state_providers(block_property_data)
