"""Smoke test script for Phase 0 verification.
Tests:
1. Groq API connection and chat completion
2. Vector / Semantic Similarity calculation
3. Headless Selenium Chromium browser loading a test URL
"""

import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings


def test_groq():
    print("\n--- 1. Testing Groq LLM API ---")
    from groq import Groq

    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is not set in .env")

    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": "Say 'GROQ_OK'"}],
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
    result = (response.choices[0].message.content or "").strip()
    print(f"✅ Groq Model: {settings.llm_model}")
    print(f"✅ Groq Output: {result}")
    assert len(result) > 0, "Empty response content from Groq"
    return True


def test_vector_similarity():
    print("\n--- 2. Testing Vector / Semantic Similarity ---")
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    corpus = [
        "HDFC Mid-Cap Opportunities Fund expense ratio is 0.74%",
        "Exit load for HDFC Small Cap Fund is 1% if redeemed within 1 year",
        "Minimum SIP amount for HDFC Large Cap Fund is 500 rupees",
    ]
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(corpus)

    query = "What is the expense ratio of HDFC Mid Cap?"
    q_vec = vectorizer.transform([query])

    sims = cosine_similarity(q_vec, X)[0]
    best_idx = int(np.argmax(sims))
    best_score = float(sims[best_idx])

    print(f"✅ Query: '{query}'")
    print(f"✅ Best Match (index {best_idx}): '{corpus[best_idx]}'")
    print(f"✅ Cosine Similarity: {best_score:.4f}")
    assert best_idx == 0
    assert best_score > 0.3
    return True


def test_selenium_headless():
    print("\n--- 3. Testing Headless Selenium ---")
    from selenium import webdriver

    if settings.browser_type.lower() == "edge":
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.edge.service import Service as EdgeService
        from webdriver_manager.microsoft import EdgeChromiumDriverManager

        options = EdgeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        service = EdgeService(EdgeChromiumDriverManager().install())
        driver = webdriver.Edge(service=service, options=options)
    else:
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.chrome.service import Service as ChromeService
        from webdriver_manager.chrome import ChromeDriverManager

        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://example.com")
        title = driver.title
        print(f"✅ Selenium Loaded ({settings.browser_type}): https://example.com")
        print(f"✅ Page Title: '{title}'")
        assert "Example" in title
    finally:
        driver.quit()
    return True


def main():
    print("========================================")
    print("Mutual Fund FAQ Assistant — Phase 0 Smoke Test")
    print("========================================")

    all_passed = True

    try:
        test_groq()
    except Exception as e:
        print(f"❌ Groq Test Failed: {e}")
        all_passed = False

    try:
        test_vector_similarity()
    except Exception as e:
        print(f"❌ Vector Similarity Test Failed: {e}")
        all_passed = False

    try:
        test_selenium_headless()
    except Exception as e:
        print(f"❌ Selenium Test Failed: {e}")
        all_passed = False

    print("\n========================================")
    if all_passed:
        print("🎉 ALL PHASE 0 CHECKS PASSED SUCCESSFULLY!")
        print("========================================")
        sys.exit(0)
    else:
        print("❌ SOME CHECKS FAILED.")
        print("========================================")
        sys.exit(1)


if __name__ == "__main__":
    main()
