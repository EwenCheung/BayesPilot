import os
import random
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMBINE_DIR = os.path.join(BASE_DIR, 'combine')

os.makedirs(COMBINE_DIR, exist_ok=True)

# Set random seed for reproducible shuffling
random.seed(42)

def merge_and_shuffle(file_paths, output_path):
    all_lines = []
    for fp in file_paths:
        with open(fp, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            all_lines.extend(lines)
            print(f"Loaded {len(lines)} lines from {os.path.relpath(fp, BASE_DIR)}")
    
    random.shuffle(all_lines)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in all_lines:
            f.write(line + '\n')
            
    print(f"Successfully written {len(all_lines)} shuffled lines to {os.path.relpath(output_path, BASE_DIR)}\n")
    return len(all_lines)

if __name__ == '__main__':
    train_files = [
        os.path.join(BASE_DIR, 'freeform_v1', 'train.jsonl'),
        os.path.join(BASE_DIR, 'resplit_60_20_20', 'train.jsonl'),
    ]
    train_out = os.path.join(COMBINE_DIR, 'train.jsonl')
    merge_and_shuffle(train_files, train_out)

    val_files = [
        os.path.join(BASE_DIR, 'freeform_v1', 'validation.jsonl'),
        os.path.join(BASE_DIR, 'resplit_60_20_20', 'validation.jsonl'),
    ]
    val_out = os.path.join(COMBINE_DIR, 'validation.jsonl')
    merge_and_shuffle(val_files, val_out)
