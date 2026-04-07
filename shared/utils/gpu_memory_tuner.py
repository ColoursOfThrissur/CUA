"""GPU Memory Auto-Tuning - Detects available GPU memory and adjusts worker count."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GPUMemoryTuner:
    """Auto-tunes execution parameters based on available GPU memory."""
    
    def __init__(self):
        self._gpu_memory_gb: Optional[float] = None
        self._recommended_workers: Optional[int] = None
        self._detect_gpu_memory()
    
    def _detect_gpu_memory(self) -> None:
        """Detect available GPU memory using multiple backends."""
        # Try NVIDIA first
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                memory_mb = float(result.stdout.strip().split('\n')[0])
                self._gpu_memory_gb = memory_mb / 1024
                logger.info(f"[GPU_TUNER] Detected NVIDIA GPU: {self._gpu_memory_gb:.1f} GB")
                return
        except Exception as e:
            logger.debug(f"[GPU_TUNER] NVIDIA detection failed: {e}")
        
        # Try AMD ROCm
        try:
            import subprocess
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse ROCm output (format varies)
                for line in result.stdout.split('\n'):
                    if 'Total' in line or 'VRAM' in line:
                        # Extract number in MB or GB
                        import re
                        match = re.search(r'(\d+)\s*(MB|GB)', line, re.IGNORECASE)
                        if match:
                            value = float(match.group(1))
                            unit = match.group(2).upper()
                            self._gpu_memory_gb = value if unit == 'GB' else value / 1024
                            logger.info(f"[GPU_TUNER] Detected AMD GPU: {self._gpu_memory_gb:.1f} GB")
                            return
        except Exception as e:
            logger.debug(f"[GPU_TUNER] AMD ROCm detection failed: {e}")
        
        # Try PyTorch CUDA
        try:
            import torch
            if torch.cuda.is_available():
                memory_bytes = torch.cuda.get_device_properties(0).total_memory
                self._gpu_memory_gb = memory_bytes / (1024 ** 3)
                logger.info(f"[GPU_TUNER] Detected GPU via PyTorch: {self._gpu_memory_gb:.1f} GB")
                return
        except Exception as e:
            logger.debug(f"[GPU_TUNER] PyTorch CUDA detection failed: {e}")
        
        logger.warning("[GPU_TUNER] No GPU detected - using CPU-optimized defaults")
        self._gpu_memory_gb = None
    
    def get_recommended_workers(self, default: int = 4) -> int:
        """Get recommended worker count based on GPU memory.
        
        Tuning strategy:
        - < 6 GB:  1 worker  (low VRAM, avoid thrashing)
        - 6-12 GB: 2 workers (mid-range GPU)
        - 12-24 GB: 3 workers (high-end consumer GPU)
        - > 24 GB: 4 workers (datacenter GPU or CPU fallback)
        """
        if self._recommended_workers is not None:
            return self._recommended_workers
        
        if self._gpu_memory_gb is None:
            # No GPU detected - use default (likely cloud LLM or CPU)
            self._recommended_workers = default
            logger.info(f"[GPU_TUNER] No GPU - using default workers: {default}")
            return self._recommended_workers
        
        if self._gpu_memory_gb < 6:
            self._recommended_workers = 1
        elif self._gpu_memory_gb < 12:
            self._recommended_workers = 2
        elif self._gpu_memory_gb < 24:
            self._recommended_workers = 3
        else:
            self._recommended_workers = 4
        
        logger.info(
            f"[GPU_TUNER] GPU memory: {self._gpu_memory_gb:.1f} GB -> "
            f"recommended workers: {self._recommended_workers}"
        )
        return self._recommended_workers
    
    def get_gpu_memory_gb(self) -> Optional[float]:
        """Get detected GPU memory in GB, or None if no GPU."""
        return self._gpu_memory_gb
    
    def has_gpu(self) -> bool:
        """Check if GPU was detected."""
        return self._gpu_memory_gb is not None


# Global instance
_tuner: Optional[GPUMemoryTuner] = None


def get_gpu_tuner() -> GPUMemoryTuner:
    """Get global GPU tuner instance."""
    global _tuner
    if _tuner is None:
        _tuner = GPUMemoryTuner()
    return _tuner
