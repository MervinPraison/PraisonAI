import os
import fnmatch
import yaml
from pathlib import Path
import logging

# Set up logging
logger = logging.getLogger(__name__)
log_level = os.getenv("LOGLEVEL", "INFO").upper()
logger.handlers = []

# Set up logging to console
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Set the logging level for the logger
logger.setLevel(log_level)

class ContextGatherer:
    def __init__(self, directory='.', output_file='context.txt',
                 relevant_extensions=None, max_file_size=1_000_000, max_tokens=900000):
        self.directory = directory
        self.output_file = output_file
        self.relevant_extensions = relevant_extensions or [
            '.py', '.js', '.ts', '.java', '.rb', '.php', '.pl', '.pm', '.c', '.h',
            '.cpp', '.hpp', '.cs', '.vb', '.swift', '.kt', '.m', '.mm', '.go', '.rs',
            '.hs', '.r', '.lua', '.sh', '.bat', '.clj', '.scala', '.erl', '.ex',
            '.ml', '.fs', '.groovy', '.jsm', '.jsx', '.tsx', '.yaml'
        ]
        self.max_file_size = max_file_size
        self.max_tokens = int(os.getenv("PRAISONAI_MAX_TOKENS", max_tokens))
        self.ignore_patterns = self.get_ignore_patterns()
        self.include_paths = self.get_include_paths()
        self.included_files = []

    def get_ignore_patterns(self):
        """
        Loads ignore patterns from various sources, prioritizing them in
        the following order:
            1. .praisonignore
            2. settings.yaml (under code.ignore_files)
            3. PRAISONAI_IGNORE_FILES environment variable
            4. .gitignore
            5. Default patterns
        """
        ignore_patterns = []

        def load_from_file(filepath):
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    ignore_patterns.extend(
                        line.strip() for line in f 
                        if line.strip() and not line.startswith('#')
                    )

        # 1. Load from .praisonignore
        load_from_file(os.path.join(self.directory, '.praisonignore'))

        # 2. Load from settings.yaml
        settings_path = os.path.join(self.directory, 'settings.yaml')
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                settings = yaml.safe_load(f)
                if 'code' in settings and 'ignore_files' in settings['code']:
                    ignore_patterns.extend(settings['code']['ignore_files'])

        # 3. Load from environment variable
        ignore_files_env = os.getenv("PRAISONAI_IGNORE_FILES")
        if ignore_files_env:
            ignore_patterns.extend(ignore_files_env.split(","))

        # 4. Load from .gitignore
        load_from_file(os.path.join(self.directory, '.gitignore'))

        # 5. Default patterns (only if no patterns loaded from above sources)
        if not ignore_patterns:
            ignore_patterns = [
                ".*", "*.pyc", "__pycache__", ".git", ".gitignore", ".vscode",
                ".idea", ".DS_Store", "*.lock", "*.pyc", ".env", "docs", "tests", 
                "test", "tmp", "temp", "*.txt", "*.md", "*.json", "*.csv", "*.tsv",
                "public", "*.sql", "*.sqlite", "*.db", "*.db3", "*.sqlite3", 
                "*.log", "*.zip", "*.gz", "*.tar", "*.rar", "*.7z", "*.pdf", 
                "*.jpg", "*.jpeg", "*.png", "*.gif", "*.svg", "cookbooks", 
                "assets", "__pycache__", "dist", "build", "node_modules", "venv"
            ]
            logger.debug(f"Using default ignore patterns: {ignore_patterns}")

        # Modify patterns to match directories and add leading '*' if necessary
        modified_ignore_patterns = [
            '*' + pattern if not pattern.startswith('.') and not pattern.startswith('*') else pattern
            for pattern in ignore_patterns
        ]
        logger.debug(f"Final ignore patterns: {modified_ignore_patterns}")
        return modified_ignore_patterns

    def get_include_paths(self):
        """
        Loads include paths from:
            1. .praisoninclude (includes ONLY files/directories listed)
            2. .praisoncontext (if .praisoninclude doesn't exist, this is used
               to include all other relevant files, excluding ignore patterns)
        """
        include_paths = []
        include_all = False  # Flag to indicate if we need to include all files
 
        include_file = os.path.join(self.directory, '.praisoncontext')
        if os.path.exists(include_file):
            with open(include_file, 'r') as f:
                include_paths.extend(
                    line.strip() for line in f
                    if line.strip() and not line.startswith('#')
                )
 
        # If .praisoncontext doesn't exist, fall back to .praisoninclude
        # for including all relevant files
        if not include_paths: 
            include_file = os.path.join(self.directory, '.praisoninclude')
            if os.path.exists(include_file):
                with open(include_file, 'r') as f:
                    include_paths.extend(
                        line.strip() for line in f
                        if line.strip() and not line.startswith('#')
                    )
                include_all = True  # Include all files along with specified paths
 
        return include_paths, include_all

    def should_ignore(self, file_path):
        """
        Check if a file or directory should be ignored based on patterns.
        Handles both file names and directory names for more comprehensive filtering.
        """
        relative_path = os.path.relpath(file_path, self.directory)
        if relative_path.startswith('.'):
            return True
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(relative_path, pattern) or \
               fnmatch.fnmatch(os.path.basename(file_path), pattern):
                return True
        return False

    def is_relevant_file(self, file_path):
        """Determine if a file is relevant for the context."""
        return os.path.isfile(file_path) and \
               os.path.getsize(file_path) <= self.max_file_size and \
               any(file_path.endswith(ext) for ext in self.relevant_extensions)

    def gather_context(self):
        """
        Gather context from relevant files, respecting ignore patterns
        and include options from .praisoninclude and .praisoncontext.
        """
        context = []
        total_files = 0
        processed_files = 0
        self.include_paths, include_all = self.get_include_paths()

        def add_file_content(file_path):
            """Helper function to add file content to context."""
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    context.append(
                        f"File: {file_path}\n\n{content}\n\n{'=' * 50}\n"
                    )
                    self.included_files.append(
                        Path(file_path).relative_to(self.directory)
                    )
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        def process_path(path):
            """Helper function to process a single path (file or directory)."""
            nonlocal total_files, processed_files
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    total_files += len(files)
                    dirs[:] = [
                        d
                        for d in dirs
                        if not self.should_ignore(os.path.join(root, d))
                    ]
                    for file in files:
                        file_path = os.path.join(root, file)
                        if not self.should_ignore(file_path) and self.is_relevant_file(file_path):
                            add_file_content(file_path)
                        processed_files += 1
                        print(
                            f"\rProcessed {processed_files}/{total_files} files",
                            end="",
                            flush=True,
                        )
            elif os.path.isfile(path) and self.is_relevant_file(path):
                add_file_content(path)
                processed_files += 1
                print(
                    f"\rProcessed {processed_files}/1 files",
                    end="",
                    flush=True,
                )

        if include_all:
            # Include ALL relevant files from the entire directory
            process_path(self.directory)
            
            # Include files from .praisoninclude specifically
            for include_path in self.include_paths:
                full_path = os.path.join(self.directory, include_path)
                process_path(full_path)
        elif self.include_paths:
            # Include only files specified in .praisoncontext
            for include_path in self.include_paths:
                full_path = os.path.join(self.directory, include_path)
                process_path(full_path)
        else:
            # No include options, process the entire directory
            process_path(self.directory)

        print()  # New line after progress indicator
        return "\n".join(context)

    def count_tokens(self, text):
        """Count tokens using a simple whitespace-based tokenizer."""
        return len(text.split())

    def truncate_context(self, context):
        """Truncate context to stay within the token limit."""
        tokens = context.split()
        if len(tokens) > self.max_tokens:
            truncated_context = ' '.join(tokens[:self.max_tokens])
            logger.warning("Context truncated due to token limit.")
            return truncated_context
        return context

    def save_context(self, context):
        """Save the gathered context to a file."""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(context)

    def get_context_tree(self):
        """Generate a formatted tree structure of included files and folders."""
        tree = []
        start_dir = Path(self.directory)

        def add_to_tree(path, prefix=''):
            contents = sorted(path.iterdir())
            pointers = [('└── ' if i == len(contents) - 1 else '├── ') for i in range(len(contents))]
            for pointer, item in zip(pointers, contents):
                rel_path = item.relative_to(start_dir)
                if rel_path in self.included_files:
                    tree.append(f"{prefix}{pointer}{rel_path}")

                if item.is_dir():
                    add_to_tree(item, prefix + ('    ' if pointer == '└── ' else '│   '))

        add_to_tree(start_dir)
        return '\n'.join(tree)

    def run(self):
        """Execute the context gathering, truncation, and reporting."""
        context = self.gather_context()
        context = self.truncate_context(context)
        token_count = self.count_tokens(context)
        print(f"Context gathered successfully.")
        print(f"Total number of tokens (estimated): {token_count}")
        # self.save_context(context)
        context_tree = self.get_context_tree()
        logger.debug(f"Context tree:\n{context_tree}")
        return context, token_count, context_tree

def main():
    gatherer = ContextGatherer()
    context, token_count, context_tree = gatherer.run()
    print(context_tree)
    print(f"\nThe context contains approximately {token_count} tokens.")
    print("First 500 characters of context:")
    print(context[:500] + "...")

if __name__ == "__main__":
    main()
