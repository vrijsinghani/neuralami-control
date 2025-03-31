from typing import Dict, Any, Type, List
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
import json
import logging
from django.conf import settings
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from apps.common.utils import get_llm
import re
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

class BusinessCredibilityToolSchema(BaseModel):
    """Input schema for BusinessCredibilityTool."""
    text_content: str = Field(..., description="The text content to analyze")
    html_content: str = Field(..., description="The HTML content to analyze")

class BusinessCredibilityTool(BaseTool):
    name: str = "Business Credibility Detector Tool"
    description: str = """
    Analyzes website content to detect business credibility signals including
    contact information, years in business, certifications, reviews, and services.
    """
    args_schema: Type[BaseModel] = BusinessCredibilityToolSchema

    def _extract_schema(self, html_content: str) -> Dict[str, Any]:
        """Extracts structured data (JSON-LD, potentially Microdata later) from HTML."""
        extracted_data = {
            "json-ld": []
            # Add keys for microdata, etc. later
        }
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract JSON-LD
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    if data:
                        # Store as list if top-level is list, else wrap in list
                        if isinstance(data, list):
                            extracted_data["json-ld"].extend(data)
                        else:
                            extracted_data["json-ld"].append(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON-LD: {e} - Content: {script.string[:100]}...")
                except Exception as e:
                     logger.warning(f"Error processing JSON-LD script: {e}")

            # Placeholder for Microdata extraction later

        except Exception as e:
            logger.error(f"Error during schema extraction: {e}", exc_info=True)
            
        logger.debug(f"Extracted Schema.org Data (JSON-LD): {json.dumps(extracted_data['json-ld'])[:300]}...")
        return extracted_data

    def _process_schema(self, extracted_schema: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Processes extracted schema data to identify relevant types."""
        processed_data = {
            "LocalBusiness": [],
            "Service": [],
            "Product": [],
            "Review": [],
            "AggregateRating": [],
            # Add other relevant types if needed
        }
        target_types = set(processed_data.keys())

        # Process JSON-LD
        for item in extracted_schema.get("json-ld", []):
            item_types = item.get("@type", [])
            # Ensure item_types is a list
            if isinstance(item_types, str):
                item_types = [item_types]
            
            found_target_type = None
            for item_type in item_types:
                if item_type in target_types:
                    found_target_type = item_type
                    break # Found a relevant type for this item
            
            if found_target_type:
                processed_data[found_target_type].append(item)
                logger.debug(f"Found relevant schema type: {found_target_type}")

        # Placeholder for processing Microdata later

        logger.debug(f"Processed Schema Results: Found { {k: len(v) for k, v in processed_data.items() if v} }")
        return processed_data

    def _preprocess_content(self, text_content: str, html_content: str) -> Dict[str, Any]:
        """Pre-process content to detect common business information patterns."""
        # Phone number patterns
        phone_patterns = [
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # 123-456-7890 or 1234567890
            r'\(\d{3}\)\s*\d{3}[-.]?\d{4}',     # (123) 456-7890
            r'\b\d{3}\s+\d{3}\s+\d{4}\b'        # 123 456 7890
        ]
        
        # Address patterns
        address_patterns = [
            r'\d+\s+[A-Za-z0-9\s,]+(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Circle|Cir|Trail|Trl|Highway|Hwy|Route|Rte)[,.\s]+(?:[A-Za-z\s]+,\s*)?[A-Z]{2}\s+\d{5}(?:-\d{4})?',
            r'\d+\s+[A-Za-z\s]+(?:Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Circle|Cir|Trail|Trl|Highway|Hwy|Route|Rte)'
        ]
        
        # Business hours patterns
        hours_patterns = [
            r'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*(?:day)?[-:\s]+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)[-\s]+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))',
            r'\b(?:\d{1,2}:\d{2}|(?:1[0-2]|0?[1-9])(?::\d{2})?\s*(?:am|pm|AM|PM))[-\s]+(?:\d{1,2}:\d{2}|(?:1[0-2]|0?[1-9])(?::\d{2})?\s*(?:am|pm|AM|PM))'
        ]

        # Initialize results
        results = {
            "has_phone": False,
            "has_address": False,
            "has_hours": False,
            "found_patterns": {
                "phones": [],
                "addresses": [],
                "hours": []
            }
        }

        # Check footer and contact sections first
        if html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            footer = soup.find('footer')
            contact_section = soup.find(id=lambda x: x and 'contact' in x.lower()) or \
                            soup.find(class_=lambda x: x and 'contact' in x.lower())
            
            priority_sections = []
            if footer:
                priority_sections.append(footer.get_text())
            if contact_section:
                priority_sections.append(contact_section.get_text())
            
            # Check priority sections first
            for section in priority_sections:
                # Check phone patterns
                for pattern in phone_patterns:
                    phones = re.findall(pattern, section)
                    if phones:
                        results["has_phone"] = True
                        results["found_patterns"]["phones"].extend(phones)
                
                # Check address patterns
                for pattern in address_patterns:
                    addresses = re.findall(pattern, section)
                    if addresses:
                        results["has_address"] = True
                        results["found_patterns"]["addresses"].extend(addresses)
                
                # Check hours patterns
                for pattern in hours_patterns:
                    hours = re.findall(pattern, section)
                    if hours:
                        results["has_hours"] = True
                        results["found_patterns"]["hours"].extend(hours)

        # If not found in priority sections, check entire content
        if not (results["has_phone"] and results["has_address"] and results["has_hours"]):
            # Check phone patterns
            for pattern in phone_patterns:
                phones = re.findall(pattern, text_content)
                if phones:
                    results["has_phone"] = True
                    results["found_patterns"]["phones"].extend(phones)
            
            # Check address patterns
            for pattern in address_patterns:
                addresses = re.findall(pattern, text_content)
                if addresses:
                    results["has_address"] = True
                    results["found_patterns"]["addresses"].extend(addresses)
            
            # Check hours patterns
            for pattern in hours_patterns:
                hours = re.findall(pattern, text_content)
                if hours:
                    results["has_hours"] = True
                    results["found_patterns"]["hours"].extend(hours)

        # Remove duplicates
        results["found_patterns"]["phones"] = list(set(results["found_patterns"]["phones"]))
        results["found_patterns"]["addresses"] = list(set(results["found_patterns"]["addresses"]))
        results["found_patterns"]["hours"] = list(set(results["found_patterns"]["hours"]))

        return results

    def _run(
        self,
        text_content: str,
        html_content: str
    ) -> str:
        try:    
            # --- Initialization ---\n            credibility_signals = {\n                \"business_info\": False,\n                \"years_in_business\": False,\n                \"customer_reviews\": False,\n                \"services_list\": False,\n                \"certifications\": False # Assuming certifications is a desired signal\n            }\n            signal_details = {\n                \"business_info\": {\"phones\": [], \"addresses\": [], \"hours\": []},\n                \"years_in_business\": None,\n                \"customer_reviews\": {\"reviews\": [], \"aggregate\": None},\n                \"services_list\": [],\n                \"certifications\": []\n            }\n            \n            # --- 1. Schema Extraction and Processing ---\n            extracted_schema = self._extract_schema(html_content)\n            processed_schema = self._process_schema(extracted_schema)\n\n            # --- 2. Populate Signals/Details from Processed Schema ---\n            # LocalBusiness Check\n            if processed_schema[\"LocalBusiness\"]:\n                lb = processed_schema[\"LocalBusiness\"][0] # Assume first one is primary\n                phone = lb.get(\"telephone\")\n                address = lb.get(\"address\") # Can be text or PostalAddress object\n                hours = lb.get(\"openingHoursSpecification\") or lb.get(\"openingHours\")\n                founding_date_str = lb.get(\"foundingDate\") or lb.get(\"startDate\")\n                awards = lb.get(\"award\") or lb.get(\"awards\") # Handle plurals\n                memberships = lb.get(\"memberOf\")\n                offers = lb.get(\"makesOffer\") or lb.get(\"hasOfferCatalog\")\n\n                if phone:\n                    credibility_signals[\"business_info\"] = True\n                    signal_details[\"business_info\"][\"phones\"].append(str(phone))\n                if address:\n                    credibility_signals[\"business_info\"] = True\n                    # Extract address string representation\n                    if isinstance(address, dict):\n                         addr_parts = [address.get(\'streetAddress\'), address.get(\'addressLocality\'), address.get(\'addressRegion\'), address.get(\'postalCode\')]\n                         signal_details[\"business_info\"][\"addresses\"].append(\", \".join(filter(None, addr_parts)))\n                    else:\n                         signal_details[\"business_info\"][\"addresses\"].append(str(address))\n                if hours:\n                    credibility_signals[\"business_info\"] = True\n                    signal_details[\"business_info\"][\"hours\"].append(str(hours)) # Store raw schema for now\n                \n                if founding_date_str:\n                    try:\n                        founding_year = int(datetime.strptime(founding_date_str, \'%Y-%m-%d\').year) # Assuming YYYY-MM-DD\n                        current_year = datetime.now().year\n                        years = current_year - founding_year\n                        if years >= 0:\n                             credibility_signals[\"years_in_business\"] = True\n                             signal_details[\"years_in_business\"] = f\"{years} years (since {founding_year})\"\n                    except ValueError: # Handle other date formats or just year\n                         try: \n                              founding_year = int(founding_date_str) # Check if it's just YYYY\n                              current_year = datetime.now().year\n                              years = current_year - founding_year\n                              if years >= 0:\n                                   credibility_signals[\"years_in_business\"] = True\n                                   signal_details[\"years_in_business\"] = f\"{years} years (since {founding_year})\"\n                         except ValueError:\n                              logger.warning(f\"Could not parse foundingDate: {founding_date_str}\")\n                              signal_details[\"years_in_business\"] = f\"Date found: {founding_date_str}\" # Store raw if unparseable\n\n                if awards:\n                    credibility_signals[\"certifications\"] = True\n                    signal_details[\"certifications\"].extend([str(a) for a in awards] if isinstance(awards, list) else [str(awards)])\n                if memberships:\n                    credibility_signals[\"certifications\"] = True\n                    # memberships can be Organization or ProgramMembership\n                    member_details = []\n                    members_list = memberships if isinstance(memberships, list) else [memberships]\n                    for member in members_list:\n                         if isinstance(member, dict):\n                              member_details.append(member.get(\'name\') or member.get(\'programName\') or str(member))\n                         else:\n                              member_details.append(str(member))\n                    signal_details[\"certifications\"].extend(filter(None, member_details))\n                \n                if offers:\n                     credibility_signals[\"services_list\"] = True\n                     # Extract offer names/details if possible\n                     offer_details = []\n                     offers_list = offers if isinstance(offers, list) else [offers]\n                     for offer in offers_list:\n                          if isinstance(offer, dict):\n                               item_offered = offer.get(\'itemOffered\')\n                               if isinstance(item_offered, dict):\n                                    offer_details.append(item_offered.get(\'name\') or str(item_offered))\n                               elif item_offered:\n                                    offer_details.append(str(item_offered))\n                               elif offer.get(\'name\'): \n                                    offer_details.append(offer.get(\'name\'))\n                               else:\n                                    offer_details.append(str(offer))\n                          else:\n                               offer_details.append(str(offer))\n                     signal_details[\"services_list\"].extend(filter(None, offer_details))\n\n            # Service/Product Check\n            if processed_schema[\"Service\"] or processed_schema[\"Product\"]:\n                credibility_signals[\"services_list\"] = True\n                for service in processed_schema[\"Service\"]:\n                    signal_details[\"services_list\"].append(service.get(\"name\") or str(service))\n                for product in processed_schema[\"Product\"]:\n                     signal_details[\"services_list\"].append(product.get(\"name\") or str(product))\n\n            # Review/AggregateRating Check\n            if processed_schema[\"Review\"]:\n                credibility_signals[\"customer_reviews\"] = True\n                signal_details[\"customer_reviews\"][\"reviews\"] = processed_schema[\"Review\"] # Store full review objects\n            if processed_schema[\"AggregateRating\"]:\n                agg = processed_schema[\"AggregateRating\"][0] # Assume one\n                if agg.get(\"reviewCount\", 0) > 0 or agg.get(\"ratingValue\") is not None:\n                     credibility_signals[\"customer_reviews\"] = True\n                     signal_details[\"customer_reviews\"][\"aggregate\"] = agg\n            \n            # --- 3. Regex Fallback for Business Info ---\n            if not credibility_signals[\"business_info\"]:\n                 logger.debug(\"Schema did not contain business info, running regex preprocessing...\")\n                 preprocessed = self._preprocess_content(text_content, html_content)\n                 if preprocessed[\"has_phone\"] or preprocessed[\"has_address\"] or preprocessed[\"has_hours\"]:\n                      credibility_signals[\"business_info\"] = True\n                      # Merge regex findings if schema was empty for these\n                      if not signal_details[\"business_info\"][\"phones\"]:\n                           signal_details[\"business_info\"][\"phones\"] = preprocessed[\"found_patterns\"][\"phones\"]\n                      if not signal_details[\"business_info\"][\"addresses\"]:\n                           signal_details[\"business_info\"][\"addresses\"] = preprocessed[\"found_patterns\"][\"addresses\"]\n                      if not signal_details[\"business_info\"][\"hours\"]:\n                           signal_details[\"business_info\"][\"hours\"] = preprocessed[\"found_patterns\"][\"hours\"]\n                      logger.debug(\"Found business info via regex fallback.\")\n                 else:\n                      logger.debug(\"Regex preprocessing did not find business info either.\")\n\n            # --- 4. Determine Missing Signals ---\n            missing_signals = [k for k, v in credibility_signals.items() if not v and k != \"business_info\"] # Exclude business_info here, handle it differently\n            # Check if specific parts of business_info are missing even if flag is True\n            if credibility_signals[\"business_info\"]:\n                 if not signal_details[\"business_info\"][\"phones\"]:\n                      missing_signals.append(\"business_info_phone\")\n                 if not signal_details[\"business_info\"][\"addresses\"]:\n                      missing_signals.append(\"business_info_address\")\n                 if not signal_details[\"business_info\"][\"hours\"]:\n                      missing_signals.append(\"business_info_hours\")\n            elif not credibility_signals[\"business_info\"]: # If business_info is completely False\n                 missing_signals.extend([\"business_info_phone\", \"business_info_address\", \"business_info_hours\"]) \n\n            # --- 5. Conditional LLM Call ---\n            if missing_signals:\n                logger.debug(f\"Signals missing after Schema/Regex: {missing_signals}. Querying LLM...\")\n                # Get LLM\n                llm, _ = get_llm(model_name=settings.BUSINESS_CREDIBILITY_MODEL, temperature=0.0)\n\n                # Define signal mapping for prompt\n                signal_prompt_map = {\n                    \"years_in_business\": \"- Years in business/establishment date\",\n                    \"customer_reviews\": \"- Customer reviews/testimonials\",\n                    \"services_list\": \"- Services/products offered\",\n                    \"certifications\": \"- Professional certifications/licenses/awards/memberships\",\n                    \"business_info_phone\": \"- Business phone number\",\n                    \"business_info_address\": \"- Business physical address\",\n                    \"business_info_hours\": \"- Business operating hours\"\n                }\n                missing_signals_text = \"\\n\".join([signal_prompt_map[s] for s in missing_signals if s in signal_prompt_map])\n\n                # Create tailored prompt\n                llm_prompt = ChatPromptTemplate.from_messages([\n                    (\"system\", \"\"\"You are an expert business analyst detecting specific missing credibility signals from website content.\n                    You will be told which signals were already found via structured data or regex. Focus ONLY on finding the signals listed under 'Signals to Find'.\n                    Analyze the HTML and Text content provided, paying attention to navigation, footers, contact/about sections, and common page structures.\n                    Return your analysis ONLY for the requested missing signals as a clean JSON object like this: {\"found_signals\": {\"signal_name\": boolean}, \"details\": {\"signal_name\": \"details found or null\"}}. Do not include markdown formatting.\"\"\"),\n                    (\"human\", \"\"\"\n                    Signals already found: {found_signals_summary}\n                    \n                    Signals to Find:\n                    {missing_signals_list}\n                    \n                    Analyze the website content below to find the missing signals listed above.\n                    \n                    Text Content:\n                    {text_content}\n                    \n                    HTML Content:\n                    {html_content}\n                    \"\"\")\n                ])\n                \n                found_signals_summary = {k: v for k,v in credibility_signals.items() if v}\n                \n                llm_chain = llm_prompt | llm | StrOutputParser()\n                llm_result_str = llm_chain.invoke({\n                    \"found_signals_summary\": json.dumps(found_signals_summary),\n                    \"missing_signals_list\": missing_signals_text,\n                    \"text_content\": text_content,\n                    \"html_content\": html_content\n                })\n                \n                # Clean and parse LLM result\n                llm_result_str = llm_result_str.strip().removeprefix(\"```json\").removesuffix(\"```\").strip()\n                try:\n                    llm_data = json.loads(llm_result_str)\n                    llm_found_signals = llm_data.get(\"found_signals\", {})\n                    llm_details = llm_data.get(\"details\", {})\n                    logger.debug(f\"LLM Analysis Result for Missing Signals: {llm_data}\")\n\n                    # Merge LLM findings\n                    merged_business_info = False\n                    for signal in missing_signals:\n                        llm_signal_key = signal # Use the potentially compound key like \"business_info_phone\"\n                        if llm_signal_key in llm_found_signals and llm_found_signals[llm_signal_key]:\n                            if signal.startswith(\"business_info_\"):\n                                part = signal.split(\"_\")[-1] + \"s\" # e.g., phones, addresses, hours\n                                if part in signal_details[\"business_info\"] and not signal_details[\"business_info\"][part]:\n                                     signal_details[\"business_info\"][part].append(llm_details.get(llm_signal_key, \"Found by LLM\"))\n                                     credibility_signals[\"business_info\"] = True # Mark main flag if any part is found\n                                     merged_business_info = True\n                            elif signal in credibility_signals:\n                                 credibility_signals[signal] = True\n                                 if signal in signal_details and not signal_details[signal]: # Avoid overwriting schema/regex details unless empty\n                                      signal_details[signal] = llm_details.get(llm_signal_key) or \"Found by LLM\"\n                    if merged_business_info:\n                         logger.debug(\"Updated business_info details based on LLM findings.\")\n                    \n                except json.JSONDecodeError as e:\n                    logger.error(f\"Failed to parse LLM response for missing signals: {e} - Response: {llm_result_str[:200]}...\")\n                except Exception as e:\
                    logger.error(f\"Error processing LLM response for missing signals: {e}\", exc_info=True)\n            else:\n                 logger.debug(\"No missing signals found after Schema/Regex check. Skipping LLM.\")\n\n            # --- 6. Combine Results ---\n            final_result = {\n                \"credibility_signals\": credibility_signals,\n                \"signal_details\": signal_details\n            }\n            \n            logger.debug(f\"Final Business credibility analysis result: {json.dumps(final_result)[:300]}...\")\n            return json.dumps(final_result)\n\n        except Exception as e:\n            logger.error(f\"Error in BusinessCredibilityTool _run: {str(e)}\", exc_info=True)\n            # Return consistent error structure\n            return json.dumps({\n                \"credibility_signals\": {k: False for k in credibility_signals} if 'credibility_signals' in locals() else {},\n                \"signal_details\": {k: None for k in signal_details} if 'signal_details' in locals() else {},\n                \"error\": \"Credibility analysis failed\",\n                \"message\": str(e)\n            })\n
