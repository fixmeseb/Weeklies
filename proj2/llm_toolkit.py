import os
import time
import platform
import warnings
from proj2 import config

# Configure PyTorch for Windows stability BEFORE importing torch
if platform.system() == "Windows":
    # Disable OpenMP to prevent multi-threading issues
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"
    # Disable torch compile optimization which can cause issues on Windows
    os.environ["TORCH_COMPILE"] = "0"

# Now import torch with Windows settings applied
try:
    import torch
    torch.set_num_threads(1)
except ImportError:
    torch = None

# Import transformers with error handling
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
except (ImportError, OSError):
    TRANSFORMERS_AVAILABLE = False
    AutoModelForCausalLM = None
    AutoTokenizer = None


class LLMUnavailableError(Exception):
    """Raised when LLM is unavailable and fallback must be used"""
    pass


class LLM:
    """
    LLM class for local language model interactions
    with Windows compatibility and GPU support
    """

    ## LLM parameters - prioritize CUDA > MPS (Apple Silicon) > CPU
    _platform = platform.system()
    if torch and torch.cuda.is_available():
        device = "cuda"
    elif torch and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    ## Model id; set WEEKLIES_LLM_MODEL to override (default in proj2/config.py).
    model = config.llm_model()

    def __init__(self, tokens: int = 500):
        """
        Initializes the LLM with the specified number of tokens
        Uses GPU if available, otherwise falls back to CPU or mock

        Args:
            tokens (int): The max number of generated characters
        """
        self.tokens = tokens
        self.tokenizer = None
        self.model_instance = None
        self._use_fallback = False
        
        # Skip real model loading if transformers not available
        if not TRANSFORMERS_AVAILABLE:
            warnings.warn(
                "Transformers not available. Using fallback mock LLM for menu generation.",
                RuntimeWarning
            )
            self._use_fallback = True
            print(f"LLM fallback mode activated (transformers unavailable)")
            return
        
        try:
            print(f"Loading LLM on device: {self.device}")
            cache_dir = os.path.join(os.path.dirname(__file__), ".hf_cache")
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model, cache_dir=cache_dir
            )

            # Load model with appropriate device configuration
            if self.device == "cuda":
                # CUDA for NVIDIA GPUs - use device_map="auto" for optimal memory usage
                print(f"Loading model to CUDA (GPU)...")
                self.model_instance = AutoModelForCausalLM.from_pretrained(
                    self.model, 
                    cache_dir=cache_dir,
                    device_map="auto",  # Automatically splits model across available GPUs
                    torch_dtype=torch.float16  # Use fp16 for GPU efficiency
                )
            elif self.device == "mps":
                # MPS (Metal Performance Shaders) for Apple Silicon
                print(f"Loading model to MPS (Apple GPU)...")
                self.model_instance = AutoModelForCausalLM.from_pretrained(
                    self.model, cache_dir=cache_dir
                )
                self.model_instance = self.model_instance.to(self.device)
            else:
                # CPU fallback - avoid device_map="cpu" which causes issues on Windows
                # Instead load without device_map and let it use default device
                print(f"Loading model to CPU...")
                self.model_instance = AutoModelForCausalLM.from_pretrained(
                    self.model, 
                    cache_dir=cache_dir,
                    low_cpu_mem_usage=True  # Reduces CPU memory during loading
                )

            self.model_instance.eval()
            print(f"LLM initialized successfully on device: {self.device}")
            
        except Exception as e:
            # If model loading fails, use fallback
            warnings.warn(
                f"LLM model loading failed ({str(e)[:100]}). "
                f"Using fallback mock LLM for menu generation.",
                RuntimeWarning
            )
            self._use_fallback = True
            print(f"LLM fallback mode activated (compatibility mode)")

    def generate(self, context: str, prompt: str) -> str:
        """
        Uses the local LLM to generate text based on the provided context and prompt
        Falls back to deterministic selection if model is unavailable

        Args:
            context (str): The system context to provide to the LLM
            prompt (str): The user prompt to provide to the LLM

        Returns:
            str: The raw, unformatted output from the LLM or fallback
        """
        if self._use_fallback or self.model_instance is None:
            return self._generate_fallback(context, prompt)
        
        start = time.time()
        try:
            chat = [
                {"role": "system", "content": context},
                {"role": "user", "content": prompt},
            ]
            chat = self.tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
            # tokenize the text
            input_tokens = self.tokenizer(chat, return_tensors="pt").to(self.device)
            # generate output tokens
            output = self.model_instance.generate(**input_tokens, max_new_tokens=self.tokens)
            # decode output tokens into text
            output = self.tokenizer.batch_decode(output)[0]
            end = time.time()
            print("Menu Item selected in %.4f seconds" % (end - start))
            return output
        except Exception as e:
            # If generation fails, fall back to deterministic method
            warnings.warn(f"LLM generation failed: {str(e)[:100]}. Using fallback.", RuntimeWarning)
            return self._generate_fallback(context, prompt)

    def _generate_fallback(self, context: str, prompt: str) -> str:
        """
        Fallback menu generation when LLM is unavailable
        Extracts item IDs from context and selects one deterministically
        
        Args:
            context (str): CSV context with menu items
            prompt (str): User prompt (contains preferences)
            
        Returns:
            str: Mock LLM output with selected item ID
        """
        # Extract item IDs from context (CSV format)
        lines = context.strip().split('\n')
        if len(lines) <= 1:  # Only header or no data
            return "<|start_of_role|>assistant<|end_of_role|>1<|end_of_text|>"
        
        # Parse CSV to get item IDs
        item_ids = []
        for line in lines[1:]:  # Skip header
            parts = line.split(',')
            if parts:
                try:
                    item_id = int(parts[0])
                    item_ids.append(item_id)
                except (ValueError, IndexError):
                    continue
        
        if not item_ids:
            return "<|start_of_role|>assistant<|end_of_role|>1<|end_of_text|>"
        
        # Deterministically select first available item
        # This ensures consistent behavior but doesn't use user preferences
        selected_id = item_ids[0]
        start = time.time()
        end = time.time()
        print("Menu Item selected in %.4f seconds (fallback)" % (end - start))
        return f"<|start_of_role|>assistant<|end_of_role|>{selected_id}<|end_of_text|>"
