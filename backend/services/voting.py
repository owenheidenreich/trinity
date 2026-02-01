"""
Trinity Backend - Self-Consistency Voting
Generate multiple candidates and select the most consistent answer
"""

import logging
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from config import VOTING_CANDIDATES, VOTING_TEMPERATURES, VOTING_MIN_COMPLEXITY
from services.embeddings import embed_text, cosine_similarity

logger = logging.getLogger(__name__)


class VotingResult:
    """Result of self-consistency voting."""
    
    def __init__(self, selected_answer: str, confidence: float,
                 candidates: List[str], scores: List[float]):
        self.selected_answer = selected_answer
        self.confidence = confidence
        self.candidates = candidates
        self.scores = scores
        self.alternatives_considered = len(candidates)
    
    def to_dict(self) -> Dict:
        return {
            'answer': self.selected_answer,
            'confidence': self.confidence,
            'alternatives_considered': self.alternatives_considered,
            'consistency_scores': self.scores
        }


def generate_candidates_parallel(
    generate_fn,
    prompt: str,
    n_candidates: int = VOTING_CANDIDATES,
    temperatures: List[float] = None,
    timeout: int = 120
) -> List[str]:
    """
    Generate multiple answer candidates in parallel with different temperatures.
    
    Args:
        generate_fn: Function that takes (prompt, temperature) and returns text
        prompt: The prompt to generate from
        n_candidates: Number of candidates to generate
        temperatures: List of temperatures to use (cycles if shorter than n_candidates)
        timeout: Maximum time per generation
        
    Returns:
        List of generated candidate answers
    """
    if temperatures is None:
        temperatures = VOTING_TEMPERATURES
    
    candidates = []
    
    def generate_one(temp_idx: int) -> Optional[str]:
        temp = temperatures[temp_idx % len(temperatures)]
        try:
            result = generate_fn(prompt, temp)
            return result
        except Exception as e:
            logger.warning(f'Candidate generation failed at temp {temp}: {e}')
            return None
    
    # Generate in parallel
    with ThreadPoolExecutor(max_workers=n_candidates) as executor:
        futures = {
            executor.submit(generate_one, i): i 
            for i in range(n_candidates)
        }
        
        for future in as_completed(futures, timeout=timeout):
            try:
                result = future.result(timeout=10)
                if result:
                    candidates.append(result)
            except Exception as e:
                logger.warning(f'Candidate retrieval failed: {e}')
    
    return candidates


def compute_consistency_scores(candidates: List[str]) -> List[float]:
    """
    Compute consistency scores for each candidate.
    
    Consistency is measured as average semantic similarity to all other candidates.
    Higher consistency means the answer is more aligned with what other generations
    produced, suggesting it's more likely to be correct.
    
    Args:
        candidates: List of candidate answers
        
    Returns:
        List of consistency scores (0-1) for each candidate
    """
    if len(candidates) <= 1:
        return [1.0] * len(candidates)
    
    # Embed all candidates
    embeddings = []
    for candidate in candidates:
        # Use first 1000 chars for embedding
        emb = embed_text(candidate[:1000])
        embeddings.append(emb)
    
    # Compute pairwise similarities
    scores = []
    for i, emb_i in enumerate(embeddings):
        if emb_i is None:
            scores.append(0.0)
            continue
        
        similarities = []
        for j, emb_j in enumerate(embeddings):
            if i != j and emb_j is not None:
                sim = cosine_similarity(emb_i, emb_j)
                similarities.append(sim)
        
        # Average similarity to others
        if similarities:
            scores.append(sum(similarities) / len(similarities))
        else:
            scores.append(0.0)
    
    return scores


def select_best_candidate(candidates: List[str], scores: List[float]) -> Tuple[str, float, int]:
    """
    Select the best candidate based on consistency scores.
    
    Args:
        candidates: List of candidate answers
        scores: List of consistency scores
        
    Returns:
        Tuple of (best_answer, confidence, index)
    """
    if not candidates:
        return '', 0.0, -1
    
    if len(candidates) == 1:
        return candidates[0], 1.0, 0
    
    # Find highest scoring candidate
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    best_answer = candidates[best_idx]
    confidence = scores[best_idx]
    
    return best_answer, confidence, best_idx


def should_use_voting(complexity: int) -> bool:
    """
    Determine if voting should be used based on question complexity.
    
    Args:
        complexity: Complexity score (1-10)
        
    Returns:
        True if voting should be used
    """
    return complexity >= VOTING_MIN_COMPLEXITY


def run_voting_pipeline(
    generate_fn,
    prompt: str,
    complexity: int = 5,
    n_candidates: int = VOTING_CANDIDATES,
    force_voting: bool = False
) -> VotingResult:
    """
    Run the full voting pipeline.
    
    Args:
        generate_fn: Function that takes (prompt, temperature) and returns text
        prompt: The prompt to generate from
        complexity: Question complexity (1-10)
        n_candidates: Number of candidates to generate
        force_voting: Force voting even for simple questions
        
    Returns:
        VotingResult with selected answer and metadata
    """
    # Check if voting is needed
    if not force_voting and not should_use_voting(complexity):
        # Simple question - just generate once
        logger.info(f'Skipping voting for complexity {complexity}')
        try:
            answer = generate_fn(prompt, 0.7)  # Default temperature
            return VotingResult(
                selected_answer=answer,
                confidence=1.0,
                candidates=[answer],
                scores=[1.0]
            )
        except Exception as e:
            logger.error(f'Single generation failed: {e}')
            return VotingResult('', 0.0, [], [])
    
    # Generate candidates
    logger.info(f'Running voting with {n_candidates} candidates')
    start_time = time.time()
    
    candidates = generate_candidates_parallel(
        generate_fn=generate_fn,
        prompt=prompt,
        n_candidates=n_candidates
    )
    
    if not candidates:
        logger.error('No candidates generated')
        return VotingResult('', 0.0, [], [])
    
    logger.info(f'Generated {len(candidates)} candidates in {time.time() - start_time:.1f}s')
    
    # Compute consistency scores
    scores = compute_consistency_scores(candidates)
    
    # Select best
    best_answer, confidence, best_idx = select_best_candidate(candidates, scores)
    
    logger.info(f'Selected candidate {best_idx} with confidence {confidence:.2f}')
    
    return VotingResult(
        selected_answer=best_answer,
        confidence=confidence,
        candidates=candidates,
        scores=scores
    )


def needs_refinement(voting_result: VotingResult, threshold: float = 0.5) -> bool:
    """
    Check if the voting result needs refinement due to low confidence.
    
    Args:
        voting_result: Result from voting pipeline
        threshold: Minimum confidence threshold
        
    Returns:
        True if refinement is recommended
    """
    return voting_result.confidence < threshold


# Module availability flag for graceful degradation
V4_VOTING_AVAILABLE = True
