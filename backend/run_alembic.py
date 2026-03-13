import traceback
import sys
from alembic.config import main

def run():
    try:
        main(prog='alembic', argv=['upgrade', 'head'])
    except Exception as e:
        with open('alembic_error_trace.txt', 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)

if __name__ == '__main__':
    run()
