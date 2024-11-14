import os
from pynvml import *

import schemas

from typing import List

# initialize NVML
nvmlInit()

try:
    device_count = nvmlDeviceGetCount()
    print(f"Device count: {device_count}")
except NVMLError as error:
    print(error)
    exit(1)


def get_vram_information() -> List[schemas.GPUStats]:
    gpu_stats = []
    for i in range(device_count):
        handle = nvmlDeviceGetHandleByIndex(i)
        gpu_name = nvmlDeviceGetName(handle)
        memory_info = nvmlDeviceGetMemoryInfo(handle)
        gpu_stats.append(
            schemas.GPUStats(
                gpu_name=gpu_name,
                total_memory=int(memory_info.total),
                free_memory=int(memory_info.free),
                used_memory=int(memory_info.used),
            )
        )
    return gpu_stats
