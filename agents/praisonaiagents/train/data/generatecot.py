from typing import Dict, Optional
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