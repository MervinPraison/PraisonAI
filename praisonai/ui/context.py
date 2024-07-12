import os
import fnmatch
import re

class ContextGatherer:
    def __init__(self, directory='.', output_file='context.txt',
                 relevant_extensions=None, max_file_size=1_000_000, max_tokens=60000):
        self.directory = directory
        self.output_file = output_file
        self.relevant_extensions = relevant_extensions or ['.py']
        self.max_file_size = max_file_size
        self.max_tokens = max_tokens
        self.ignore_patterns = self.get_ignore_patterns()

    def get_ignore_patterns(self):
        """Read .gitignore file and return ignore patterns."""
        default_patterns = [".*", "*.pyc", "__pycache__", ".git", ".gitignore", ".vscode",
                            ".idea", ".DS_Store", "*.lock", "*.pyc", ".env",
                            "docs", "tests", "test", "tmp", "temp", 
                            "*.txt", "*.md", "*.json", "*.csv", "*.tsv", "*.yaml", "*.yml","public",
                            "*.sql", "*.sqlite", "*.db", "*.db3", "*.sqlite3", "*.log", "*.zip", "*.gz",
                            "*.tar", "*.rar", "*.7z", "*.pdf", "*.jpg", "*.jpeg", "*.png", "*.gif", "*.svg",
                            "cookbooks", "assets", "__pycache__", "dist", "build", "node_modules", "venv",]
        gitignore_path = os.path.join(self.directory, '.gitignore')
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r') as f:
                gitignore_patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            return list(set(default_patterns + gitignore_patterns))
        return default_patterns

    def should_ignore(self, file_path):
        """Check if a file should be ignored based on patterns."""
        relative_path = os.path.relpath(file_path, self.directory)
        if relative_path.startswith('.'):
            return True
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(relative_path, pattern):
                return True
        return False

    def is_relevant_file(self, file_path):
        """Determine if a file is relevant for the context."""
        if os.path.getsize(file_path) > self.max_file_size:
            return False
        return any(file_path.endswith(ext) for ext in self.relevant_extensions)

    def gather_context(self):
        """Gather context from relevant files in the directory."""
        context = []
        total_files = sum(len(files) for _, _, files in os.walk(self.directory))
        processed_files = 0

        for root, dirs, files in os.walk(self.directory):
            dirs[:] = [d for d in dirs if not self.should_ignore(os.path.join(root, d))]
            for file in files:
                file_path = os.path.join(root, file)
                if not self.should_ignore(file_path) and self.is_relevant_file(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            context.append(f"File: {file_path}\n\n{content}\n\n{'='*50}\n")
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")
                processed_files += 1
                print(f"\rProcessed {processed_files}/{total_files} files", end="", flush=True)
        print()  # New line after progress indicator
        return '\n'.join(context)

    def count_tokens(self, text):
        """Count the number of tokens in the given text using a simple tokenizer."""
        # Split on whitespace and punctuation
        tokens = re.findall(r'\b\w+\b|[^\w\s]', text)
        return len(tokens)

    def truncate_context(self, context):
        """Truncate context to fit within the specified token limit."""
        tokens = re.findall(r'\b\w+\b|[^\w\s]', context)
        if len(tokens) > self.max_tokens:
            truncated_tokens = tokens[:self.max_tokens]
            return ' '.join(truncated_tokens)
        return context

    def save_context(self, context):
        """Save the gathered context to a file."""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(context)
            
    def get_context_tree(self):
        """Generate a formatted tree structure of the folder, including only relevant files."""
        tree = []
        start_dir = os.path.abspath(self.directory)
        
        def add_to_tree(path, prefix=''):
            contents = sorted(os.listdir(path))
            pointers = [('└── ' if i == len(contents) - 1 else '├── ') for i in range(len(contents))]
            for pointer, name in zip(pointers, contents):
                full_path = os.path.join(path, name)
                if self.should_ignore(full_path):
                    continue
                
                rel_path = os.path.relpath(full_path, start_dir)
                tree.append(f"{prefix}{pointer}{name}")
                
                if os.path.isdir(full_path):
                    add_to_tree(full_path, prefix + ('    ' if pointer == '└── ' else '│   '))
                elif self.is_relevant_file(full_path):
                    continue  # We've already added the file to the tree

        add_to_tree(start_dir)
        return '\n'.join(tree)

    def run(self):
        """Run the context gathering process and return the context and token count."""
        context = self.gather_context()
        context = self.truncate_context(context)
        token_count = self.count_tokens(context)
        print(f"Context gathered successfully.")
        print(f"Total number of tokens (estimated): {token_count}")
        # self.save_context(context)
        context_tree = self.get_context_tree()
        print("\nContext Tree Structure:")
        print(context_tree)
        
        return context, token_count, context_tree

def main():
    gatherer = ContextGatherer(
        directory='.',
        output_file='context.txt',
        relevant_extensions=['.py'],
        max_file_size=500_000,  # 500KB
        max_tokens=60000
    )
    context, token_count, context_tree = gatherer.run()
    print(f"\nThe context contains approximately {token_count} tokens.")
    print("First 500 characters of context:")
    print(context[:500] + "...")

if __name__ == "__main__":
    main()