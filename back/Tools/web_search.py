##
## EPITECH PROJECT, 2026
## mirror-sensai
## File description:
## web_search.py
##

# web_search.py

import os
import requests


SEARCH_ENGINES = {
    "1": {
        "id": "brave",
        "name": "Brave Search",
        "description": "Recherche Web généraliste",
        "api_key_env": "BRAVE_SEARCH_API_KEY",
    },
    "2": {
        "id": "tavily",
        "name": "Tavily",
        "description": "Recherche optimisée pour les applications IA",
        "api_key_env": "TAVILY_API_KEY",
    },
    "3": {
        "id": "exa",
        "name": "Exa",
        "description": "Recherche sémantique et découverte de contenus",
        "api_key_env": "EXA_API_KEY",
    },
}

def print_search_moteur(session):
    """Display all available search engines and the current selection."""

    print("\n=== Available search engines ===")

    engines = list(SEARCH_ENGINES.values())

    for number, engine in enumerate(engines, start=1):
        if engine["id"] == session.search_motor:
            status = " <-- current"
        else:
            status = ""

        print(
            f"{number}. {engine['name']} "
            f"({engine['id']}) - "
            f"{engine['description']}{status}"
        )

    print("\nUse /switch_search [name|number] to change the search engine.")

def switch_search_motor(session, argument: str = None):
    """
    Switch the search engine using its name or number.

    Usage:
        /switch_search [name|number]
    """

    engines = list(SEARCH_ENGINES.values())

    # No argument: display available search engines.
    if not argument:
        print("Available search engines:")

        for number, engine in enumerate(engines, start=1):
            current = (
                " (current)"
                if engine["id"] == session.search_motor
                else ""
            )

            print(
                f"  {number}. {engine['name']} "
                f"({engine['id']}){current}"
            )

        print("\nUsage: /switch_search [name|number]")
        return

    argument = argument.strip().lower()

    # Select by number.
    if argument.isdigit():
        index = int(argument) - 1

        if 0 <= index < len(engines):
            selected_engine = engines[index]
        else:
            print(
                f"Invalid search engine number: {argument}. "
                f"Choose a number between 1 and {len(engines)}."
            )
            return

    # Select by name or ID.
    else:
        selected_engine = next(
            (
                engine
                for engine in engines
                if argument == engine["id"].lower()
                or argument == engine["name"].lower()
            ),
            None,
        )

        if selected_engine is None:
            available = ", ".join(
                f"{i}. {engine['id']}"
                for i, engine in enumerate(engines, start=1)
            )

            print(f"Unknown search engine: {argument}")
            print(f"Available search engines: {available}")
            return

    # Update the session.
    session.search_motor = selected_engine["id"]

    print(
        f"Search engine switched to: {selected_engine['name']} "
        f"({selected_engine['id']})"
    )



def _search_brave(query: str, api_key: str) -> list[dict]:
    """Effectue une recherche via Brave Search API."""

    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        params={
            "q": query,
            "count": 10,
            "search_lang": "fr",
            "country": "FR",
        },
        timeout=15,
    )

    response.raise_for_status()
    data = response.json()

    results = []

    for item in data.get("web", {}).get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })

    return results

def _search_tavily(query: str, api_key: str) -> list[dict]:
    """Effectue une recherche via Tavily API."""

    response = requests.post(
        "https://api.tavily.com/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "search_depth": "basic",
            "max_results": 10,
            "include_answer": False,
        },
        timeout=15,
    )

    response.raise_for_status()
    data = response.json()

    results = []

    for item in data.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
        })

    return results

def _search_exa(query: str, api_key: str) -> list[dict]:
    """Effectue une recherche via Exa API."""

    response = requests.post(
        "https://api.exa.ai/search",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "type": "auto",
            "numResults": 10,
            "contents": {
                "text": {
                    "maxCharacters": 1000,
                }
            },
        },
        timeout=15,
    )

    response.raise_for_status()
    data = response.json()

    results = []

    for item in data.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("text", ""),
        })

    return results

def process_search_results(results: list[dict]) -> list[dict]:
    """
    Nettoie et normalise les résultats de recherche en conservant
    toutes les métadonnées disponibles.

    Args:
        results: Liste de résultats normalisés provenant d'un moteur.

    Returns:
        Liste de résultats nettoyés, avec les métadonnées conservées.
    """

    processed = []
    seen_urls = set()

    for result in results:
        url = result.get("url", "").strip()

        # Ignorer les résultats sans URL.
        if not url:
            continue

        # Supprimer les doublons.
        if url in seen_urls:
            continue

        seen_urls.add(url)

        # Copier le résultat pour conserver toutes ses métadonnées.
        cleaned_result = result.copy()

        # Nettoyer les champs textuels principaux.
        cleaned_result["title"] = result.get("title", "").strip()
        cleaned_result["url"] = url
        cleaned_result["snippet"] = result.get("snippet", "").strip()

        processed.append(cleaned_result)

    return processed



def search_internet(query: str, engine: str) -> list[dict]:
    """
    Recherche des informations sur Internet avec le moteur choisi.

    Args:
        query: Recherche à effectuer.
        engine: Identifiant du moteur (brave, tavily ou exa).

    Returns:
        Liste de résultats normalisés :
        [
            {
                "title": str,
                "url": str,
                "snippet": str
            }
        ]

    Raises:
        ValueError: Si la requête ou le moteur est invalide.
        RuntimeError: En cas de problème avec l'API.
    """

    query = query.strip()

    if not query:
        raise ValueError("The search query cannot be empty.")

    # Normalisation de l'identifiant du moteur.
    engine = engine.strip().lower()

    available_engines = {
        value["id"] for value in SEARCH_ENGINES.values()
    }

    if engine not in available_engines:
        raise ValueError(
            f"Unknown search engine '{engine}'. "
            f"Available engines: {', '.join(sorted(available_engines))}"
        )

    # Récupération de la configuration du moteur.
    engine_config = next(
        item
        for item in SEARCH_ENGINES.values()
        if item["id"] == engine
    )

    # Récupération de la clé API depuis les variables d'environnement.
    api_key = os.getenv(engine_config["api_key_env"])

    if not api_key:
        raise RuntimeError(
            f"Missing API key for {engine_config['name']}. "
            f"Configure the environment variable "
            f"{engine_config['api_key_env']}."
        )

    try:
        if engine == "brave":
            results = _search_brave(query, api_key)

        elif engine == "tavily":
            results = _search_tavily(query, api_key)

        elif engine == "exa":
            results = _search_exa(query, api_key)

        else:
            # Protection supplémentaire si le registre évolue.
            raise ValueError(f"Unsupported search engine: {engine}")

        return process_search_results(results)

    except requests.RequestException as exc:
        raise RuntimeError(
            f"Network error while searching with "
            f"{engine_config['name']}: {exc}"
        ) from exc
