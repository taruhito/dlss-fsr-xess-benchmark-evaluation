"""
Requirements for resolution rankings scripts:

pyiqa>=0.1.10
torch>=1.12.0
torchvision>=0.13.0
pillow>=9.0.0
numpy>=1.22 & <2 # python -m pip install numpy<2
pandas>=1.4
tqdm>=4.60
"""

import time
import sys


def main():
    try:
        import torch
    except Exception as e:
        print("PyTorch not installed:", e)
        sys.exit(1)

    print("torch version:", torch.__version__)
    # Some type checkers/linters don't recognize torch.version (CUDA version)
    torch_version = getattr(torch, "version", None)
    print("CUDA version (build):", getattr(torch_version, "cuda", None))    # torch.version
    print("torch.cuda.is_available():", torch.cuda.is_available())

    if not torch.cuda.is_available():
        print("\nCUDA is not available to PyTorch. Your script will run on CPU and VRAM will stay near baseline.")
        print("Install a CUDA-enabled build, e.g. (pip):")
        print("  pip uninstall -y torch torchvision torchaudio")
        print("  pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision torchaudio")
        return

    dev = torch.device("cuda")
    print("GPU(cuda):", torch.cuda.get_device_name(dev))
    dev = torch.device("cuda:0")
    print("GPU(cuda:0):", torch.cuda.get_device_name(dev))
    torch.cuda.empty_cache()
    time.sleep(1.0)

    # Show initial memory
    def mem():
        alloc = torch.cuda.memory_allocated(dev) / (1024**2)
        reserv = torch.cuda.memory_reserved(dev) / (1024**2)
        return alloc, reserv

    a0, r0 = mem()
    print(f"Initial -> allocated={a0:.1f} MiB reserved={r0:.1f} MiB")

    # Checker
    check = False
    answ = input("Do you want to perform a GPU memory allocation test? (y/n): ").lower()
    if answ.startswith("y"):
        check = True
    if check:
        # Allocate ~512 MiB tensors in steps + watch Task Manager move
        blocks = []
        bytes_per_float = 4
        target_mib = 512
        n_elems = target_mib * 1024 * 1024 // bytes_per_float  # ~512 MiB
        print("Allocating 3 x ~512 MiB on the GPU (about 1.5 GiB total)...")

        for i in range(3):
            t = torch.empty(n_elems, dtype=torch.float32, device=dev)
            t.fill_(i)  # do something so it really allocates
            blocks.append(t)
            a, r = mem()
            print(f" after block {i+1}: allocated={a:.1f} MiB reserved={r:.1f} MiB")
            time.sleep(2.0)

        print("Holding allocations for 15 seconds so you can check Task Manager...")
        time.sleep(15.0)

        # Free and report
        blocks.clear()
        del blocks
        try:
            del t  # remove last tensor reference from the loop
        except NameError:
            pass

        import gc
        gc.collect()
        torch.cuda.empty_cache()
        time.sleep(2.0)
        a1, r1 = mem()
        print(f"Free -> allocated={a1:.1f} MiB reserved={r1:.1f} MiB")
        
    print("Done.")

if __name__ == "__main__":
    main()
    