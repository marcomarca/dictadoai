import time
import sys
import os

# Ensure the project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class ImportProfiler:
    def __init__(self):
        self.stack = []
        self.results = []
        if isinstance(__builtins__, dict):
            self.original_import = __builtins__['__import__']
        else:
            self.original_import = getattr(__builtins__, '__import__')

    def __enter__(self):
        if isinstance(__builtins__, dict):
            __builtins__['__import__'] = self.profile_import
        else:
            setattr(__builtins__, '__import__', self.profile_import)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if isinstance(__builtins__, dict):
            __builtins__['__import__'] = self.original_import
        else:
            setattr(__builtins__, '__import__', self.original_import)

    def profile_import(self, name, *args, **kwargs):
        # We only care about modules being loaded the first time
        if name in sys.modules:
            return self.original_import(name, *args, **kwargs)

        depth = len(self.stack)
        self.stack.append(name)
        
        start = time.perf_counter()
        module = self.original_import(name, *args, **kwargs)
        duration = time.perf_counter() - start
        
        self.stack.pop()
        
        # Only record if it took more than 50ms or if it's a dictado_ai module
        if duration > 0.05 or name.startswith('dictado_ai'):
            self.results.append({
                'name': name,
                'duration': duration,
                'depth': depth
            })
            
        return module

def run_profile():
    profiler = ImportProfiler()
    
    with profiler:
        try:
            import dictado_ai.controller
        except Exception as e:
            print(f"\nError importing controller: {e}")

    all_results = profiler.results
    all_results.sort(key=lambda x: x['duration'], reverse=True)

    with open("scratch/profile_results.txt", "w", encoding="utf-8") as f:
        f.write("="*80 + "\n")
        f.write(f"{'Module Name':<60} | {'Time (s)':<10}\n")
        f.write("="*80 + "\n")
        for r in all_results:
            f.write(f"{r['name']:<60} | {r['duration']:.4f}s\n")
        
        f.write("\n--- DICTADO_AI INTERNAL MODULES ---\n")
        internal = [r for r in profiler.results if 'dictado_ai' in r['name']]
        internal.sort(key=lambda x: x['duration'], reverse=True)
        for r in internal:
            f.write(f"{r['name']:<60} | {r['duration']:.4f}s\n")

    print(f"Results saved to scratch/profile_results.txt. Total modules profiled: {len(all_results)}")

if __name__ == "__main__":
    run_profile()
