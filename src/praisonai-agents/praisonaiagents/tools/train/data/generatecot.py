from typing import Dict, Optional, Union, Any
import json
from datetime import datetime
import os
import logging

# Setup logging based on environment variable
log_level = os.getenv('LOGLEVEL', 'INFO').upper()
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Lazy loader for LLM
def get_llm():
    try:
        from praisonaiagents.llm.llm import LLM
        return LLM
    except ImportError:
        raise ImportError(
            "LLM is required for this toolbut not installed. "
            "Please install with: pip install 'praisonaiagents[llm]' datasets huggingface-hub pandas"
        )

class GenerateCOT:
    def __init__(
        self,
        qa_pairs: Optional[Dict[str, str]] = None,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        max_attempts: int = 3,
        verbose: bool = True,
        temperature: float = 0.5
    ):
        self.qa_pairs = qa_pairs or {}
        self.max_attempts = max_attempts
        self.solutions = {}
        self.llm = get_llm()(model=model)  # Get LLM class and instantiate
        self.model = model
        self.temperature = temperature
        self.verbose = verbose
        logger.debug(f"Initialized GenerateCOT with model={model}, max_attempts={max_attempts}")
        
    def _ask_ai(self, prompt: str) -> str:
        logger.debug(f"Sending prompt to LLM: {prompt[:100]}...")
        response = self.llm.response(prompt, temperature=self.temperature)
        logger.debug(f"Received response: {response[:100]}...")
        return response
        
    def _build_solution_prompt(self, question: str, context: str) -> str:
        return f"""
        Solve this problem step by step: {question}
        Context: {context}
        Steps needed:
        1. Break down the problem
        2. Show your work
        3. Explain each step
        4. Give final answer
        """

    def cot_generate(self, question: str, context: str = "") -> str:
        prompt = self._build_solution_prompt(question, context)
        return self._ask_ai(prompt)
        
    def cot_check(self, question: str, answer: str) -> bool:
        if question not in self.qa_pairs:
            raise ValueError(f"No correct answer found for: {question}")
            
        prompt = f"""
        Question: {question}
        Given Answer: {answer}
        Correct Answer: {self.qa_pairs[question]}
        Is the given answer correct? Reply only with 'true' or 'false'.
        """
        return self._ask_ai(prompt).lower().strip() == "true"
        
    def cot_find_error(self, question: str, solution: str) -> int:
        if self.cot_check(question, solution):
            return -1
            
        sentences = [s.strip() for s in solution.replace('。', '.').split('.') if s.strip()]
        left, right = 0, len(sentences)
        
        while left < right:
            mid = (left + right) // 2
            partial = '. '.join(sentences[:mid]) + '.'
            if self.cot_check(question, partial):
                left = mid + 1
            else:
                right = mid
                
        return left
        
    def cot_improve(self, question: str, current: str) -> str:
        best_solution = current
        best_score = self._rate_solution(question, current)
        attempts = 0
        
        while attempts < self.max_attempts:
            attempts += 1
            new_solution = self.cot_generate(question, current)
            new_score = self._rate_solution(question, new_solution)
            
            if new_score > best_score:
                best_solution = new_solution
                best_score = new_score
                
            if best_score > 0.8:
                break
                
        return best_solution
        
    def _rate_solution(self, question: str, solution: str) -> float:
        prompt = f"""
        Rate this solution from 0 to 1:
        Question: {question}
        Solution: {solution}
        Correct Answer: {self.qa_pairs.get(question, '')}
        Return only a number between 0 and 1.
        """
        try:
            score = float(self._ask_ai(prompt))
            return min(max(score, 0), 1)
        except ValueError:
            return 0.0
            
    def cot_run(self, question: str) -> str:
        """Run COT generation for a single question."""
        solution = self.cot_generate(question)
        if self.cot_check(question, solution):
            return solution

        solution = self.cot_improve(question, solution)
        
        error_pos = self.cot_find_error(question, solution)
        if error_pos != -1:
            correct_part = '. '.join(solution.split('. ')[:error_pos]) + '.'
            solution = self.cot_generate(question, correct_part)

        self.solutions[question] = {
            "solution": solution,
            "error_position": error_pos,
        }
        return solution
        
    def cot_load_answers(self, filepath: str) -> bool:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.qa_pairs.update(data)
            return True
        except Exception as e:
            print(f"Error loading answers: {e}")
            return False
            
    def _is_qa_pairs(self, qa_pairs: Any) -> bool:
        """Validate if input is a proper QA pairs dictionary."""
        if not qa_pairs:
            return True  # None or empty is valid
        if not isinstance(qa_pairs, dict):
            raise ValueError("qa_pairs must be a dictionary with questions as keys and answers as values")
        return True

    def cot_append_solutions_with_qa_pairs(
        self,
        filepath: str = 'solutions.json',
        qa_pairs: Optional[Dict[str, str]] = None
    ) -> None:
        """Appends current solutions to existing file or creates a new one."""
        try:
            self._is_qa_pairs(qa_pairs)  # Validate format
            if qa_pairs:
                self.qa_pairs.update(qa_pairs)

            data = {
                "solutions": self.solutions,
                "qa_pairs": self.qa_pairs,
                "saved_at": datetime.now().isoformat()
            }

            existing_data = {}
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                pass

            if existing_data:
                existing_data["solutions"].update(data["solutions"])
                existing_data["qa_pairs"].update(data["qa_pairs"])
                existing_data["saved_at"] = data["saved_at"]
                data = existing_data

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error appending solutions: {e}")

    def cot_save_solutions_with_qa_pairs(
        self,
        filepath: str = 'solutions.json',
        append: bool = False,
        qa_pairs: Optional[Dict[str, str]] = None
    ) -> None:
        try:
            self._is_qa_pairs(qa_pairs)  # Validate format
            if qa_pairs:
                self.qa_pairs.update(qa_pairs)

            if append:
                self.cot_append_solutions_with_qa_pairs(filepath)
                return

            data = {
                "solutions": self.solutions,
                "qa_pairs": self.qa_pairs,
                "saved_at": datetime.now().isoformat()
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving solutions: {e}")

    def cot_generate_dict(self, question: str, context: str = "") -> dict:
        prompt = self._build_solution_prompt(question, context)
        thought_process = self._ask_ai(prompt)
        
        final_answer_prompt = f"""
        Based on this solution, what is the final answer only:
        {thought_process}
        Give only the final answer, no explanation.
        """
        final_answer = self._ask_ai(final_answer_prompt)
        return {
            "thought_process": thought_process,
            "final_answer": final_answer
        }

    def cot_improve_dict(self, question: str, current_solution: str) -> dict:
        """
        Improves the existing solution (text form), returning the best dictionary-based version.
        """
        best_solution = {
            "thought_process": current_solution,
            "final_answer": current_solution
        }
        best_score = self._rate_solution(question, current_solution)
        attempts = 0

        while attempts < self.max_attempts:
            attempts += 1
            new_solution = self.cot_generate_dict(question, current_solution)
            new_score = self._rate_solution(question, new_solution["thought_process"])
            if new_score > best_score:
                best_solution = new_solution
                best_score = new_score
            if best_score > 0.8:
                break
        return best_solution

    def cot_run_dict(self, question: str) -> dict:
        """Uses the dictionary-based solution approach, storing the final solution in self.solutions."""
        logger.debug(f"Starting cot_run_dict for question: {question}")
        
        solution = self.cot_generate_dict(question)
        logger.debug(f"Initial solution generated: {str(solution)[:100]}...")
        
        if self.cot_check(question, solution["final_answer"]):
            logger.debug("Initial solution passed verification")
            self.solutions[question] = solution
            return solution

        logger.debug("Initial solution failed verification, attempting improvement")
        improved = self.cot_improve_dict(question, solution["thought_process"])
        if self.cot_check(question, improved["final_answer"]):
            logger.debug("Improved solution passed verification")
            self.solutions[question] = improved
            return improved

        logger.debug("Checking for errors in improved solution")
        error_pos = self.cot_find_error(question, improved["thought_process"])
        if error_pos != -1:
            logger.debug(f"Found error at position {error_pos}, generating final solution")
            partial_solution = '. '.join(improved["thought_process"].split('. ')[:error_pos]) + '.'
            final = self.cot_generate_dict(question, partial_solution)
            self.solutions[question] = final
            return final

        logger.debug("Using improved solution as final result")
        self.solutions[question] = improved
        return improved

    def cot_export_json_with_qa_pairs(
        self,
        filepath: str = 'dataset.json',
        save_to_file: bool = True,
        qa_pairs: Optional[Dict[str, str]] = None
    ) -> Union[str, list]:
        """
        Export solutions in Alpaca training format with their full thought process.
        """
        try:
            self._is_qa_pairs(qa_pairs)  # Validate format
            if qa_pairs:
                self.qa_pairs.update(qa_pairs)
                # Generate solutions if empty
                if not self.solutions:
                    for question in qa_pairs:
                        self.cot_run_dict(question)

            alpaca_data = []
            for question, sol in self.solutions.items():
                alpaca_data.append({
                    "instruction": question,
                    "input": "",
                    "output": sol.get("thought_process", "")
                })

            if not save_to_file:
                return alpaca_data

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(alpaca_data, f, ensure_ascii=False, indent=2)
            return filepath
        except Exception as e:
            print(f"Error exporting to Alpaca format: {e}")
            return None

    def cot_export_csv_with_qa_pairs(
        self,
        filepath: str = 'dataset.csv',
        qa_pairs: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """Export solutions in CSV format."""
        try:
            import csv
            self._is_qa_pairs(qa_pairs)  # Validate format
            if qa_pairs:
                self.qa_pairs.update(qa_pairs)
                # Generate solutions if empty
                if not self.solutions:
                    for question in qa_pairs:
                        self.cot_run_dict(question)

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['instruction', 'input', 'output'])
                for question, sol in self.solutions.items():
                    writer.writerow([question, '', sol.get("thought_process", "")])
            return filepath
        except Exception as e:
            print(f"Error exporting to CSV format: {e}")
            return None

    def cot_save(
        self,
        question: str,
        answer: str,
        filepath: str = 'dataset.csv'
    ) -> Optional[str]:
        """Save a single question-answer pair with chain of thought to CSV file."""
        logger.debug(f"Saving QA pair to {filepath}")
        try:
            self.qa_pairs[question] = answer
            logger.debug("Added QA pair to internal dictionary")
            
            solution = self.cot_run_dict(question)
            logger.debug("Generated solution for question")
            
            import csv
            import os
            file_exists = os.path.exists(filepath)
            logger.debug(f"File exists: {file_exists}")

            with open(filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    logger.debug("Creating new file with headers")
                    writer.writerow(['instruction', 'input', 'output'])
                writer.writerow([question, '', solution.get("thought_process", "")])
                logger.debug("Wrote solution to file")
            return filepath
        except Exception as e:
            logger.error(f"Error saving to CSV: {str(e)}")
            return None

    # Rename existing function to indicate it handles qa_pairs dictionary
    def cot_append_csv_with_qa_pairs(
        self,
        filepath: str = 'dataset.csv',
        qa_pairs: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """Append solutions to CSV file using qa_pairs dictionary."""
        try:
            self._is_qa_pairs(qa_pairs)  # Validate format
            if qa_pairs:
                self.qa_pairs.update(qa_pairs)
            
            import csv
            import os
            file_exists = os.path.exists(filepath)

            with open(filepath, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['instruction', 'input', 'output'])

                for question, sol in self.solutions.items():
                    writer.writerow([question, '', sol.get("thought_process", "")])
            return filepath
        except Exception as e:
            print(f"Error appending to CSV: {e}")
            return None

    def cot_upload_to_huggingface(
        self,
        huggingface_username: str,
        dataset_name: str,
        filepath: str,
        private: bool = False
    ) -> str:
        """Upload generated solutions to HuggingFace datasets."""
        logger.debug(f"Attempting to upload {filepath} to HuggingFace as {dataset_name}")
        try:
            from datasets import Dataset
            import pandas as pd
            
            logger.debug(f"Loading data from {filepath}")
            if filepath.endswith('.csv'):
                data = pd.read_csv(filepath)
                logger.debug(f"Loaded CSV with {len(data)} rows")
            elif filepath.endswith('.json'):
                data = pd.read_json(filepath)
                logger.debug(f"Loaded JSON with {len(data)} records")
            else:
                raise ValueError("Only CSV and JSON files are supported")
                
            logger.debug("Converting to HuggingFace dataset")
            dataset = Dataset.from_pandas(data)
            
            repo_id = f"{huggingface_username}/{dataset_name}"
            logger.debug(f"Pushing to hub: {repo_id}")
            dataset.push_to_hub(
                repo_id,
                private=private
            )
            
            logger.debug("Upload completed successfully")
            return f"Dataset uploaded successfully to {repo_id}"
            
        except Exception as e:
            logger.error(f"Error uploading to HuggingFace: {str(e)}")
            return None

# Usage example:
if __name__ == "__main__":
    # Direct QA Pairs Export Example
    print("\n=== Direct QA Pairs Export Example ===")
    direct_qa_data = {
        "Number of r's in the word strawberry": "3"
    }
    
    direct_generator = GenerateCOT()

    # Export with qa_pairs passed directly to functions
    direct_generator.cot_export_csv_with_qa_pairs(
        filepath='direct_solutions.csv',
        qa_pairs=direct_qa_data
    )
    
    # Example of using cot_save for a single QA pair
    direct_generator.cot_save(
        question="What is the capital of France?",
        answer="Paris",
        filepath="single_qa.csv"
    )
    

    
    # Upload to HuggingFace
    direct_generator.cot_upload_to_huggingface(
        huggingface_username="mervinpraison",
        dataset_name="cot-test",
        filepath="single_qa.csv"
    )
    
    # direct_generator.cot_export_json_with_qa_pairs(
    #     filepath='direct_solutions.json',
    #     qa_pairs=direct_qa_data
    # )

    # # Rest of the original examples...
    # qa_data = {
    #     "What is 2+2?": "4",
    #     "How many letters in 'hello'?": "5"
    # }
    
    # generator = GenerateCOT(qa_pairs=qa_data)
    # for question in qa_data:
    #     solution = generator.cot_run(question)
    #     print(f"Question: {question}")
    #     print(f"Solution: {solution}\n")
    # answer = generator.cot_run("What is 2+2?")
    # print(answer)

    # # Additional QA data processing example
    # print("\n=== Processing Additional QA Data ===")
    # extra_qa_data = {

    #     "What is 5 * 3?": "15"
    # }
    
    # # Create separate generator for additional data
    # extra_generator = GenerateCOT(qa_pairs=extra_qa_data)
    
    # # Process and save solutions
    # for question in extra_qa_data:
    #     solution = extra_generator.cot_run_dict(question)
    #     print(f"Processing extra question: {question}")
    
    # # Save solutions separately
    # extra_generator.cot_save_solutions_with_qa_pairs('extra_qa_solutions.json')
    
    # # Export in Alpaca format
    # extra_generator.cot_export_json_with_qa_pairs(filepath='extra_qa_alpaca.json', save_to_file=True)
    
    # # Demonstrate loading saved data
    # loaded_generator = GenerateCOT(qa_pairs={})
    # loaded_generator.cot_load_answers('extra_qa_solutions.json')
    # print("\nLoaded extra QA pairs:", loaded_generator.qa_pairs)