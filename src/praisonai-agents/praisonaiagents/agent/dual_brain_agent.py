"""
DualBrainAgent - Agent with separate reasoning and conversational models.

This agent extends the ReasoningAgent to use different LLM models for
conversational interaction and analytical reasoning, enabling optimized
performance for different cognitive tasks.
"""

import logging
from typing import Optional, Dict, Any, Union, List
from .reasoning_agent import ReasoningAgent
from .reasoning import ReasoningConfig, ReasoningFlow
from ..tools.train.data.generatecot import GenerateCOT

logger = logging.getLogger(__name__)


class DualBrainAgent(ReasoningAgent):
    """
    Agent with dual LLM models - one for conversation, one for reasoning.
    
    This agent uses:
    - Main LLM for conversational interactions and general responses
    - Reasoning LLM for analytical thinking and complex problem solving
    
    Inherits all ReasoningAgent functionality while adding dual-model support.
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        
        # Dual brain configuration
        llm: Optional[Union[str, Any]] = None,  # Main conversational model
        reasoning_llm: Optional[Union[str, Any]] = None,  # Analytical reasoning model
        
        # LLM configuration dictionaries
        llm_config: Optional[Dict[str, Any]] = None,
        reasoning_config: Optional[Union[ReasoningConfig, Dict[str, Any]]] = None,
        
        # Other parameters
        tools: Optional[List[Any]] = None,
        reasoning: bool = True,
        reasoning_flow: Optional[ReasoningFlow] = None,
        min_confidence: float = 0.7,
        show_reasoning: bool = True,
        
        # Pass through all other parameters
        **kwargs
    ):
        """
        Initialize a DualBrainAgent.
        
        Args:
            llm: Main conversational model (e.g., "gpt-4-turbo")
            reasoning_llm: Analytical reasoning model (e.g., "o1-preview")
            llm_config: Configuration for main LLM (temperature, etc.)
            reasoning_config: Configuration for reasoning behavior and model
            **kwargs: All other parameters passed to ReasoningAgent
        """
        
        # Set default models if not provided
        main_llm = llm or "gpt-4o-mini"
        self.reasoning_llm_model = reasoning_llm or "gpt-4o-mini"
        
        # Store LLM configurations
        self.llm_config = llm_config or {"temperature": 0.7}
        
        # Handle reasoning_config - can be ReasoningConfig or dict with model info
        if isinstance(reasoning_config, dict):
            # Extract model info if present
            reasoning_model_config = reasoning_config.get("model", self.reasoning_llm_model)
            reasoning_temp = reasoning_config.get("temperature", 0.1)
            reasoning_prompt = reasoning_config.get("system_prompt")
            
            # Create ReasoningConfig from remaining parameters
            config_params = {k: v for k, v in reasoning_config.items() 
                           if k not in ["model", "temperature", "system_prompt"]}
            config_params.setdefault("temperature", reasoning_temp)
            if reasoning_prompt:
                config_params["system_prompt"] = reasoning_prompt
                
            final_reasoning_config = ReasoningConfig(**config_params)
            self.reasoning_llm_model = reasoning_model_config
            
        elif reasoning_config is None:
            final_reasoning_config = ReasoningConfig(
                confidence_threshold=min_confidence,
                style="analytical",
                temperature=0.1
            )
        else:
            final_reasoning_config = reasoning_config
        
        # Initialize parent with main LLM
        super().__init__(
            name=name or "DualBrainAgent",
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=instructions,
            llm=main_llm,
            tools=tools,
            reasoning=reasoning,
            reasoning_config=final_reasoning_config,
            reasoning_flow=reasoning_flow,
            min_confidence=min_confidence,
            show_reasoning=show_reasoning,
            **kwargs
        )
        
        # Setup reasoning-specific LLM
        self.reasoning_llm = self.reasoning_llm_model
        
        # Override COT generator to use reasoning LLM
        if self.reasoning_enabled:
            try:
                self.cot_generator = GenerateCOT(
                    model=self.reasoning_llm_model,
                    temperature=self.reasoning_config.temperature,
                    verbose=self.show_reasoning
                )
                logger.info(f"DualBrainAgent initialized - Main: {main_llm}, Reasoning: {self.reasoning_llm_model}")
            except Exception as e:
                logger.warning(f"Could not initialize COT generator with reasoning LLM: {e}")
                
        # Store model information for introspection
        self.model_info = {
            "conversational_model": main_llm,
            "reasoning_model": self.reasoning_llm_model,
            "llm_config": self.llm_config,
            "reasoning_config": final_reasoning_config
        }
    
    def _chat_with_reasoning(
        self,
        message: str,
        temperature: float,
        tools: Optional[List[Any]],
        task_name: Optional[str],
        task_description: Optional[str],
        task_id: Optional[str]
    ) -> str:
        """
        Enhanced reasoning chat that uses dual models.
        """
        
        # Step 1: Use reasoning LLM for initial analysis
        analysis_step = self.reasoning_engine.create_step(
            title="Deep Analysis",
            action="Analyze problem using specialized reasoning model",
            thought=f"Using {self.reasoning_llm_model} for analysis: {message}"
        )
        
        # Use reasoning LLM for Chain of Thought
        reasoning_result = None
        if self.cot_generator:
            try:
                reasoning_result = self.cot_generator.cot_generate_dict(message)
                analysis_step.thought = reasoning_result.get("thought_process", "")
                analysis_step.confidence = self._estimate_reasoning_confidence(reasoning_result)
                
                self.reasoning_engine.update_step(
                    analysis_step.id,
                    thought=analysis_step.thought,
                    confidence=analysis_step.confidence
                )
                
                if self.show_reasoning:
                    logger.info(f"Reasoning model analysis: {analysis_step.confidence:.2f} confidence")
                    
            except Exception as e:
                logger.warning(f"Reasoning LLM analysis failed: {e}")
                analysis_step.confidence = 0.4
        
        # Step 2: Use main LLM for conversational synthesis
        synthesis_step = self.reasoning_engine.create_step(
            title="Response Synthesis",
            action="Synthesize conversational response using main model",
            thought="",
            confidence=0.0
        )
        
        # Build synthesis prompt that includes reasoning context
        synthesis_prompt = self._build_dual_brain_prompt(message, reasoning_result)
        
        # Use main LLM for synthesis (parent's chat method)
        response = super(ReasoningAgent, self).chat(
            synthesis_prompt,
            self.llm_config.get("temperature", temperature),
            tools,
            task_name,
            task_description,
            task_id
        )
        
        synthesis_step.thought = response
        synthesis_step.confidence = self._estimate_confidence(response)
        
        # Step 3: Validation using reasoning model if confidence is low
        if synthesis_step.confidence < self.min_confidence and self.cot_generator:
            validation_step = self.reasoning_engine.create_step(
                title="Response Validation",
                action="Validate response using reasoning model",
                thought="",
                confidence=0.0
            )
            
            try:
                validation_prompt = f"""
                Original Problem: {message}
                Proposed Response: {response}
                
                Evaluate this response for accuracy, completeness, and correctness. 
                Provide a rating from 0 to 1 and suggest improvements if needed.
                """
                
                validation_result = self.cot_generator.cot_generate_dict(validation_prompt)
                validation_step.thought = validation_result.get("thought_process", "")
                validation_step.confidence = self._extract_validation_score(validation_result)
                
                # If validation suggests improvement, regenerate
                if validation_step.confidence < 0.7:
                    logger.info("Validation suggests improvement, regenerating response")
                    
                    improvement_prompt = f"""
                    {synthesis_prompt}
                    
                    Validation feedback: {validation_step.thought}
                    
                    Please improve your response based on this feedback.
                    """
                    
                    response = super(ReasoningAgent, self).chat(
                        improvement_prompt,
                        self.llm_config.get("temperature", temperature),
                        tools,
                        task_name,
                        task_description,
                        task_id
                    )
                    
                    synthesis_step.thought = response
                    synthesis_step.confidence = max(synthesis_step.confidence, validation_step.confidence)
                    
            except Exception as e:
                logger.warning(f"Response validation failed: {e}")
                validation_step.confidence = synthesis_step.confidence
        
        # Add model information to response if showing reasoning
        if self.show_reasoning:
            model_info = f"\n\n--- Dual Brain Process ---\n"
            model_info += f"Analysis Model: {self.reasoning_llm_model}\n"
            model_info += f"Response Model: {self.llm}\n"
            model_info += self._format_reasoning_summary()
            response = f"{response}{model_info}"
        
        return response
    
    def _build_dual_brain_prompt(self, original_message: str, reasoning_result: Optional[Dict]) -> str:
        """Build a prompt that incorporates reasoning model insights."""
        
        base_prompt = original_message
        
        if reasoning_result:
            thought_process = reasoning_result.get("thought_process", "")
            final_answer = reasoning_result.get("final_answer", "")
            
            base_prompt = f"""
            Original Question: {original_message}
            
            Reasoning Analysis (from specialized reasoning model):
            {thought_process}
            
            Reasoning Conclusion: {final_answer}
            
            Based on this analytical foundation, provide a clear, conversational response that:
            1. Addresses the original question directly
            2. Incorporates the insights from the reasoning analysis
            3. Uses an appropriate tone and style for the user
            4. Ensures accuracy while remaining accessible
            """
        
        return base_prompt
    
    def _estimate_reasoning_confidence(self, reasoning_result: Dict) -> float:
        """Estimate confidence from reasoning model output."""
        if not reasoning_result:
            return 0.0
            
        thought_process = reasoning_result.get("thought_process", "")
        final_answer = reasoning_result.get("final_answer", "")
        
        # Base confidence on structure and content
        confidence = 0.5
        
        # Detailed thought process increases confidence
        if len(thought_process) > 200:
            confidence += 0.2
        if len(thought_process) > 500:
            confidence += 0.1
            
        # Clear final answer increases confidence
        if final_answer and len(final_answer) > 10:
            confidence += 0.1
            
        # Look for reasoning indicators
        reasoning_indicators = ["because", "therefore", "analysis", "step", "consider", "evaluate"]
        indicator_count = sum(1 for indicator in reasoning_indicators 
                            if indicator in thought_process.lower())
        confidence += min(0.2, indicator_count * 0.05)
        
        return max(0.0, min(1.0, confidence))
    
    def _extract_validation_score(self, validation_result: Dict) -> float:
        """Extract numerical validation score from validation result."""
        thought_process = validation_result.get("thought_process", "")
        
        # Look for explicit ratings
        import re
        
        # Look for patterns like "rating: 0.8" or "score: 7/10"
        rating_patterns = [
            r"rating[:\s]+([0-9]*\.?[0-9]+)",
            r"score[:\s]+([0-9]*\.?[0-9]+)",
            r"confidence[:\s]+([0-9]*\.?[0-9]+)",
            r"([0-9]*\.?[0-9]+)\s*out\s*of\s*[0-9]+",
            r"([0-9]*\.?[0-9]+)/[0-9]+"
        ]
        
        for pattern in rating_patterns:
            matches = re.findall(pattern, thought_process.lower())
            if matches:
                try:
                    score = float(matches[0])
                    # Normalize to 0-1 range
                    if score > 1:
                        score = score / 10.0
                    return max(0.0, min(1.0, score))
                except ValueError:
                    continue
        
        # Default confidence based on content analysis
        return self._estimate_confidence(thought_process)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the dual models being used."""
        return self.model_info.copy()
    
    def switch_reasoning_model(self, new_model: str):
        """Switch the reasoning model at runtime."""
        self.reasoning_llm_model = new_model
        self.reasoning_llm = new_model
        self.model_info["reasoning_model"] = new_model
        
        # Reinitialize COT generator
        if self.reasoning_enabled:
            try:
                self.cot_generator = GenerateCOT(
                    model=new_model,
                    temperature=self.reasoning_config.temperature,
                    verbose=self.show_reasoning
                )
                logger.info(f"Switched reasoning model to: {new_model}")
            except Exception as e:
                logger.error(f"Failed to switch reasoning model: {e}")
    
    def switch_conversational_model(self, new_model: str):
        """Switch the conversational model at runtime."""
        self.llm = new_model
        self.model_info["conversational_model"] = new_model
        logger.info(f"Switched conversational model to: {new_model}")
    
    @property
    def dual_brain_summary(self) -> Dict[str, Any]:
        """Get summary including dual brain statistics."""
        base_summary = self.reasoning_summary
        base_summary.update({
            "conversational_model": self.model_info["conversational_model"],
            "reasoning_model": self.model_info["reasoning_model"],
            "dual_brain_mode": True
        })
        return base_summary