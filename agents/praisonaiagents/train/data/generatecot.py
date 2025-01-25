from typing import Dict, Optional, Union
import json
from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel

class GenerateCOT:
    def __init__(
        self,
        qa_pairs: Dict[str, str],
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        max_attempts: int = 100
    ):
        self.qa_pairs = qa_pairs
        self.max_attempts = max_attempts
        self.solutions = {}
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _ask_ai(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
        
    def get_solution(self, question: str, context: str = "") -> str:
        prompt = f"""
        Solve this problem step by step: {question}
        Context: {context}
        Steps needed:
        1. Break down the problem
        2. Show your work
        3. Explain each step
        4. Give final answer
        """
        return self._ask_ai(prompt)
        
    def check_answer(self, question: str, answer: str) -> bool:
        if question not in self.qa_pairs:
            raise ValueError(f"No correct answer found for: {question}")
            
        prompt = f"""
        Question: {question}
        Given Answer: {answer}
        Correct Answer: {self.qa_pairs[question]}
        Is the given answer correct? Reply only with 'true' or 'false'.
        """
        return self._ask_ai(prompt).lower().strip() == "true"
        
    def find_error(self, question: str, solution: str) -> int:
        if self.check_answer(question, solution):
            return -1
            
        sentences = [s.strip() for s in solution.replace('。', '.').split('.') if s.strip()]
        left, right = 0, len(sentences)
        
        while left < right:
            mid = (left + right) // 2
            partial = '. '.join(sentences[:mid]) + '.'
            if self.check_answer(question, partial):
                left = mid + 1
            else:
                right = mid
                
        return left
        
    def improve_solution(self, question: str, current: str) -> str:
        best_solution = current
        best_score = self._rate_solution(question, current)
        
        for _ in range(self.max_attempts):
            new_solution = self.get_solution(question, current)
            new_score = self._rate_solution(question, new_solution)
            
            if new_score > best_score:
                best_solution = new_solution
                best_score = new_score
                
            if best_score > 0.9:
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
        except:
            return 0.0
            
    def start(self, question: str) -> str:
        solution = self.get_solution(question)
        if self.check_answer(question, solution):
            return solution
            
        solution = self.improve_solution(question, solution)
        
        error_pos = self.find_error(question, solution)
        if error_pos != -1:
            correct_part = '. '.join(solution.split('. ')[:error_pos]) + '.'
            solution = self.get_solution(question, correct_part)
            
        self.solutions[question] = {
            "solution": solution,
            "error_position": error_pos,
        }
        return solution
        
    def load_answers(self, filepath: str) -> bool:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.qa_pairs.update(data)
            return True
        except Exception as e:
            print(f"Error loading answers: {e}")
            return False
            
    def save_solutions(self, filepath: str = 'solutions.json') -> None:
        data = {
            "solutions": self.solutions,
            "qa_pairs": self.qa_pairs,
            "saved_at": datetime.now().isoformat()
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving solutions: {e}")

    def get_solution_dict(self, question: str, context: str = "") -> dict:
        """
        Get solution with a thought process and final answer, returning them as a dictionary.
        """
        prompt = f"""
        Solve this problem step by step: {question}
        Context: {context}
        Steps needed:
        1. Break down the problem
        2. Show your work
        3. Explain each step
        4. Give final answer
        """
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

    def improve_solution_dict(self, question: str, current_solution: str) -> dict:
        """
        Improves the existing solution (text form), returning the best dictionary-based version.
        """
        best_solution = {
            "thought_process": current_solution,
            "final_answer": current_solution
        }
        best_score = self._rate_solution(question, current_solution)

        for _ in range(self.max_attempts):
            new_solution = self.get_solution_dict(question, current_solution)
            new_score = self._rate_solution(question, new_solution["thought_process"])
            if new_score > best_score:
                best_solution = new_solution
                best_score = new_score
            if best_score > 0.9:
                break
        return best_solution

    def start_dict(self, question: str) -> dict:
        """
        Uses the dictionary-based get_solution_dict and improve_solution_dict,
        storing the final solution in self.solutions.
        """
        solution = self.get_solution_dict(question)
        if self.check_answer(question, solution["final_answer"]):
            self.solutions[question] = solution
            return solution

        improved = self.improve_solution_dict(question, solution["thought_process"])
        if self.check_answer(question, improved["final_answer"]):
            self.solutions[question] = improved
            return improved

        error_pos = self.find_error(question, improved["thought_process"])
        if error_pos != -1:
            partial_solution = '. '.join(improved["thought_process"].split('. ')[:error_pos]) + '.'
            final = self.get_solution_dict(question, partial_solution)
            self.solutions[question] = final
            return final

        self.solutions[question] = improved
        return improved

    def export_alpaca_format(self, filepath: str = None, save_to_file: bool = True) -> Union[str, list]:
        """
        Export solutions in Alpaca training format with their full thought process.
        """
        alpaca_data = []
        for question, sol in self.solutions.items():
            alpaca_data.append({
                "instruction": question,
                "input": "",
                "output": sol.get("thought_process", "")
            })

        if not save_to_file:
            return alpaca_data

        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f'alpaca_format_{timestamp}.json'

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(alpaca_data, f, ensure_ascii=False, indent=2)
            return filepath
        except Exception as e:
            print(f"Error exporting to Alpaca format: {e}")
            return None

# Usage example:
if __name__ == "__main__":
    qa_data = {
        "What is 2+2?": "4",
        "How many letters in 'hello'?": "5"
    }
    
    generator = GenerateCOT(qa_pairs=qa_data)
    for question in qa_data:
        solution = generator.start(question)
        print(f"Question: {question}")
        print(f"Solution: {solution}\n")
    answer = generator.start("What is 2+2?")
    print(answer)

    # Additional QA data processing example
    print("\n=== Processing Additional QA Data ===")
    extra_qa_data = {
        "What is the capital of France?": "Paris",
        "What is 5 * 3?": "15"
    }
    
    # Create separate generator for additional data
    extra_generator = GenerateCOT(qa_pairs=extra_qa_data)
    
    # Process and save solutions
    for question in extra_qa_data:
        solution = extra_generator.start_dict(question)
        print(f"Processing extra question: {question}")
    
    # Save solutions separately
    extra_generator.save_solutions('extra_qa_solutions.json')
    
    # Export in Alpaca format
    extra_generator.export_alpaca_format(filepath='extra_qa_alpaca.json', save_to_file=True)
    
    # Demonstrate loading saved data
    loaded_generator = GenerateCOT(qa_pairs={})
    loaded_generator.load_answers('extra_qa_solutions.json')
    print("\nLoaded extra QA pairs:", loaded_generator.qa_pairs)