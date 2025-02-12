from scrapling import Fetcher, AsyncFetcher, StealthyFetcher, PlayWrightFetcher

def clean_text(text):
    """
    Removes extraneous carriage returns, using splitlines() and join().  This
    method is more robust to different line ending conventions.

    Args:
        text: The input text.

    Returns:
        The cleaned text.
    """

    lines = text.splitlines()
    # Remove completely empty lines.
    non_empty_lines = [line for line in lines if line.strip()]
    # Join with single newline.
    cleaned_text = "\n".join(non_empty_lines)

    #Optional: if you *do* want to preserve blank lines that contain only whitespace:
    #lines = text.splitlines()
    #cleaned_text = "\n".join(lines)

    return cleaned_text


url='https://search.neuralami.com/search?q=flooring+stores+in+jacksonville'
fetcher=Fetcher()
page = fetcher.get(url)
print(clean_text(page.get_all_text(ignore_tags=('script', 'style'))))
