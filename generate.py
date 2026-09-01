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
NUMBER_PROVIDERS_FOLDER_PATH = DESTINATION_FOLDER_PATH / DATAPACK_NAMESPACE / "number_provider"


def gen_block_id_provider_and_tags(): # Generates the "block_id" number provider and its "block_id/b0-bX" block tags
    # Build block tags
    with BLOCK_VALUE_CLASSES_PATH.open("r") as f:
        data = json.load(f)

        blocks = list(data.keys())
        block_count = len(blocks)
        bit_count = math.ceil(math.log2(block_count))

        # Prepare block tags
        block_tag_data = [{"values": []} for _ in range(bit_count)] # Using EMPTY_BLOCK_TAG_CONTENT instead of {...} makes them all share a reference, so don't do that

        # Fill block tag data
        for i, block_id in enumerate(blocks):
            bits = [(i >> bit) & 1 for bit in range(bit_count - 1, -1, -1)] # Create a list of bits that represent i, taken from stackoverflow
            for j, bit in enumerate(bits):
                if bit == 1:
                    block_tag_data[j]["values"].append(block_id)

        # Write data to block tags
        folder_path = BLOCK_TAGS_FOLDER_PATH / "block_id"
        folder_path.mkdir(parents=True, exist_ok=True)

        for i in range(bit_count):
            file_path = folder_path / f"b{i}.json"
            with file_path.open("w") as f2:
                json.dump(block_tag_data[i], f2, separators=(',', ':'))

    # Build number provider
    number_provider_data = {"type":"minecraft:sum","operands":[]}
    for i in range(bit_count):
        number_provider_data["operands"].append({"type":"minecraft:number_dispatcher","cases":[{"condition":{"type":"minecraft:match_block","blocks":f"#{DATAPACK_NAMESPACE}:block_id/b{i}"},"number_provider":2**i}]})

    file_path = NUMBER_PROVIDERS_FOLDER_PATH / "block_id.json"
    with file_path.open("w") as f:
        json.dump(number_provider_data, f, separators=(',', ':'))


def gen_property_value_class_tags(): # For block state properties that have more than 1 value class, generates a block tag for every value class except the last one
    with BLOCK_VALUE_CLASSES_PATH.open("r") as t:
        block_value_data = json.load(t)

    with BLOCK_STATE_PROPERTIES_PATH.open("r") as f:
        data = json.load(f)

        for property, value_classes in data.items():
            value_classes_count = len(value_classes)
            if value_classes_count <= 1: continue

            for i in range(1, value_classes_count): # Skip the 1st instead of last one, because heuristically, earlier value classes have more block entries
                ids = [block_id for block_id, states in block_value_data.items() if states.get(property, 0) == i]
                block_tag_data = {"values": ids}

                folder_path = BLOCK_TAGS_FOLDER_PATH / "value_class" / property
                folder_path.mkdir(parents=True, exist_ok=True)

                file_path = folder_path / f"{i}.json"
                with file_path.open("w") as f2:
                    json.dump(block_tag_data, f2, separators=(',', ':'))


def gen_individual_block_state_providers():
    pass # TODO: If a block state property's value range contains 4 or more possible values, use binary search. Within the binary search (except for the highest possible layer), use a default provider so it doesn't need to check the final value or the last block tag


# Run
NUMBER_PROVIDERS_FOLDER_PATH.mkdir(parents=True, exist_ok=True)
gen_block_id_provider_and_tags()
gen_property_value_class_tags()
gen_individual_block_state_providers()
