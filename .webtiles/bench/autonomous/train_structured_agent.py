"""Launch V6 in a fresh run directory; subprocesses inherit representation."""
import os
os.environ['DCSS_REPRESENTATION'] = 'spatial-v6'
from train_crawl_agent import main

if __name__ == '__main__':
    main()
