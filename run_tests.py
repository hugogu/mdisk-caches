"""Simple test runner (no pytest required)."""
import sys
import traceback
import importlib.util


def run_tests():
    """Discover and run all test functions."""
    test_modules = [
        "tests.test_detect",
        "tests.test_recommend",
        "tests.test_mount",
        "tests.test_configure",
        "tests.test_cli",
    ]
    
    total = 0
    passed = 0
    failed = 0
    
    for module_name in test_modules:
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            print(f"SKIP  {module_name}: import failed ({e})")
            continue
        
        for attr in dir(module):
            if attr.startswith("test_"):
                total += 1
                func = getattr(module, attr)
                try:
                    func()
                    print(f"PASS  {module_name}.{attr}")
                    passed += 1
                except Exception as e:
                    print(f"FAIL  {module_name}.{attr}: {e}")
                    traceback.print_exc()
                    failed += 1
    
    print()
    print(f"{'='*50}")
    print(f"Total: {total}, Passed: {passed}, Failed: {failed}")
    print(f"{'='*50}")
    return failed == 0


if __name__ == "__main__":
    sys.path.insert(0, "src")
    ok = run_tests()
    sys.exit(0 if ok else 1)
