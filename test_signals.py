from signals import classify_with_llm, compute_stylometrics

TEST_INPUTS = [
    (
        "clearly_ai",
        "Artificial intelligence (AI) has emerged as a transformative technology with "
        "far-reaching implications across numerous sectors. It is important to note that "
        "its impact extends beyond mere automation, encompassing complex decision-making "
        "processes that were previously exclusive to human cognition. Furthermore, the "
        "integration of machine learning algorithms has enabled unprecedented advancements "
        "in data analysis and pattern recognition.",
    ),
    (
        "clearly_human",
        "i was making eggs this morning and dropped the whole carton on the floor. like, "
        "all 12. just gone. the dog was thrilled obviously. i just stood there for a second "
        "not sure if i should laugh or cry, decided on both",
    ),
    (
        "borderline_formal_human",
        "The experiment yielded results inconsistent with our initial hypothesis. We observed "
        "a statistically significant decrease in reaction time across all test groups, though "
        "the variance between groups remained high. These findings suggest the need for "
        "further investigation into the underlying mechanisms.",
    ),
    (
        "borderline_edited_ai",
        "Learning a new language in your 30s is honestly harder than I expected—but not "
        "impossible. The key, I think, is giving up on perfection early. Sure, AI tools like "
        "ChatGPT can help you draft sentences and check grammar, but real fluency comes from "
        "making mistakes in front of actual people.",
    ),
]

if __name__ == "__main__":
    print("=== Signal comparison: LLM vs Stylometrics ===\n")
    print(f"{'input':<26} {'llm_score':>10} {'stylo_score':>12} {'agree?':>8}")
    print("-" * 60)
    for label, text in TEST_INPUTS:
        llm = classify_with_llm(text)
        stylo = compute_stylometrics(text)
        llm_score = llm["ai_score"]
        stylo_score = stylo["stylometric_score"]
        # Signals agree if both lean the same direction relative to 0.5
        agree = (llm_score > 0.5) == (stylo_score > 0.5)
        print(f"{label:<26} {llm_score:>10.3f} {stylo_score:>12.4f} {'yes' if agree else 'NO':>8}")
    print()
    print("--- LLM reasoning ---")
    for label, text in TEST_INPUTS:
        result = classify_with_llm(text)
        print(f"  [{label}] {result['reasoning']}")
