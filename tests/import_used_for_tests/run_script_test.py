import os
import sys

if __name__ == '__main__':
    assert sys.argv == [__file__, '-x', 'foo'], sys.argv
    assert os.path.dirname(os.path.abspath(__file__)) in sys.path
    print('hi from run_script_test.py')
