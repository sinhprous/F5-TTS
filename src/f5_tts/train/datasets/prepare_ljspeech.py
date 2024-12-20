import os
import sys

sys.path.append(os.getcwd())

import json
import torch
from importlib.resources import files
from pathlib import Path
from tqdm import tqdm
import soundfile as sf
from datasets import Dataset
from datasets.arrow_writer import ArrowWriter
import librosa
from utils_alignment import load_alignment_model, generate_word_timestamps, word_to_character_alignment, create_attention_matrix


def main():
    alignment_model, alignment_tokenizer = load_alignment_model(
        "cuda",
        dtype=torch.float16,
    )
    
    result = []
    duration_list = []
    text_vocab_set = set()

    with open(meta_info, "r") as f:
        lines = f.readlines()[:4000]
        for line in tqdm(lines):
            uttr, text, norm_text = line.split("|")
            norm_text = norm_text.strip()
            wav_path = Path(dataset_dir) / "wavs" / f"{uttr}.wav"
            duration = sf.info(wav_path).duration
            if duration < 0.4 or duration > 30:
                continue
            
            word_timestamps = generate_word_timestamps(
                wav_path, norm_text, alignment_model, alignment_tokenizer,
            )
            char_alignments = word_to_character_alignment(word_timestamps, norm_text)
            SAMPLE_RATE = 24000
            HOP_LENGTH = 256
            len_mel = librosa.get_duration(path=wav_path) * SAMPLE_RATE // HOP_LENGTH
            attention_matrix = create_attention_matrix(char_alignments, SAMPLE_RATE, HOP_LENGTH, len_mel)
            
            result.append({"audio_path": str(wav_path), "text": norm_text, "duration": duration, "attn": attention_matrix.tolist(),})
            duration_list.append(duration)
            text_vocab_set.update(list(norm_text))

    # save preprocessed dataset to disk
    if not os.path.exists(f"{save_dir}"):
        os.makedirs(f"{save_dir}")
    print(f"\nSaving to {save_dir} ...")

    with ArrowWriter(path=f"{save_dir}/raw.arrow") as writer:
        for line in tqdm(result, desc="Writing to raw.arrow ..."):
            # writer.write(line)
            if isinstance(line, dict):  # Ensure line is a dictionary
                writer.write(line)
            else:
                raise ValueError("Each line must be a dictionary with key-value pairs.")
    
    # # Convert the result into a Dataset
    # dataset = Dataset.from_list(result)
    # # Open the ArrowWriter to write the data
    # with ArrowWriter(path=f"{save_dir}/raw.arrow") as writer:
    #     # Write the entire dataset at once
    #     writer.write_batch(dataset)

    # dup a json separately saving duration in case for DynamicBatchSampler ease
    with open(f"{save_dir}/duration.json", "w", encoding="utf-8") as f:
        json.dump({"duration": duration_list}, f, ensure_ascii=False)

    # vocab map, i.e. tokenizer
    # add alphabets and symbols (optional, if plan to ft on de/fr etc.)
    with open(f"{save_dir}/vocab.txt", "w") as f:
        for vocab in sorted(text_vocab_set):
            f.write(vocab + "\n")

    print(f"\nFor {dataset_name}, sample count: {len(result)}")
    print(f"For {dataset_name}, vocab size is: {len(text_vocab_set)}")
    print(f"For {dataset_name}, total {sum(duration_list)/3600:.2f} hours")


if __name__ == "__main__":
    tokenizer = "char"  # "pinyin" | "char"

    dataset_dir = "data/LJSpeech-1.1"
    dataset_name = f"LJSpeech_{tokenizer}"
    meta_info = os.path.join(dataset_dir, "metadata.csv")
    save_dir = str(files("f5_tts").joinpath("../../")) + f"/data/{dataset_name}"
    print(f"\nPrepare for {dataset_name}, will save to {save_dir}\n")

    main()
