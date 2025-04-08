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
            # --- Initialization ---
            credibility_signals = {
                "business_info": False,
                "years_in_business": False,
                "customer_reviews": False,
                "services_list": False,
                "certifications": False # Assuming certifications is a desired signal
            }
            signal_details = {
                "business_info": {"phones": [], "addresses": [], "hours": []},
                "years_in_business": None,
                "customer_reviews": {"reviews": [], "aggregate": None},
                "services_list": [],
                "certifications": []
            }

            # --- 1. Schema Extraction and Processing ---
            extracted_schema = self._extract_schema(html_content)
            processed_schema = self._process_schema(extracted_schema)

            # --- 2. Populate Signals/Details from Processed Schema ---
            # LocalBusiness Check
            if processed_schema["LocalBusiness"]:
                lb = processed_schema["LocalBusiness"][0] # Assume first one is primary
                phone = lb.get("telephone")
                address = lb.get("address") # Can be text or PostalAddress object
                hours = lb.get("openingHoursSpecification") or lb.get("openingHours")
                founding_date_str = lb.get("foundingDate") or lb.get("startDate")
                awards = lb.get("award") or lb.get("awards") # Handle plurals
                memberships = lb.get("memberOf")
                offers = lb.get("makesOffer") or lb.get("hasOfferCatalog")

                if phone:
                    credibility_signals["business_info"] = True
                    signal_details["business_info"]["phones"].append(str(phone))
                if address:
                    credibility_signals["business_info"] = True
                    # Extract address string representation
                    if isinstance(address, dict):
                         addr_parts = [address.get('streetAddress'), address.get('addressLocality'), address.get('addressRegion'), address.get('postalCode')]
                         signal_details["business_info"]["addresses"].append(", ".join(filter(None, addr_parts)))
                    else:
                         signal_details["business_info"]["addresses"].append(str(address))
                if hours:
                    credibility_signals["business_info"] = True
                    signal_details["business_info"]["hours"].append(str(hours)) # Store raw schema for now

                if founding_date_str:
                    try:
                        founding_year = int(datetime.strptime(founding_date_str, '%Y-%m-%d').year) # Assuming YYYY-MM-DD
                        current_year = datetime.now().year
                        years = current_year - founding_year
                        if years >= 0:
                             credibility_signals["years_in_business"] = True
                             signal_details["years_in_business"] = f"{years} years (since {founding_year})"
                    except ValueError: # Handle other date formats or just year
                         try:
                              founding_year = int(founding_date_str) # Check if it's just YYYY
                              current_year = datetime.now().year
                              years = current_year - founding_year
                              if years >= 0:
                                   credibility_signals["years_in_business"] = True
                                   signal_details["years_in_business"] = f"{years} years (since {founding_year})"
                         except ValueError:
                              logger.warning(f"Could not parse foundingDate: {founding_date_str}")
                              signal_details["years_in_business"] = f"Date found: {founding_date_str}" # Store raw if unparseable

                if awards:
                    credibility_signals["certifications"] = True
                    signal_details["certifications"].extend([str(a) for a in awards] if isinstance(awards, list) else [str(awards)])
                if memberships:
                    credibility_signals["certifications"] = True
                    # memberships can be Organization or ProgramMembership
                    member_details = []
                    members_list = memberships if isinstance(memberships, list) else [memberships]
                    for member in members_list:
                         if isinstance(member, dict):
                              member_details.append(member.get('name') or member.get('programName') or str(member))
                         else:
                              member_details.append(str(member))
                    signal_details["certifications"].extend(filter(None, member_details))

                if offers:
                     credibility_signals["services_list"] = True
                     # Extract offer names/details if possible
                     offer_details = []
                     offers_list = offers if isinstance(offers, list) else [offers]
                     for offer in offers_list:
                          if isinstance(offer, dict):
                               item_offered = offer.get('itemOffered')
                               if isinstance(item_offered, dict):
                                    offer_details.append(item_offered.get('name') or str(item_offered))
                               elif item_offered:
                                    offer_details.append(str(item_offered))
                               elif offer.get('name'):
                                    offer_details.append(offer.get('name'))
                               else:
                                    offer_details.append(str(offer))
                          else:
                               offer_details.append(str(offer))
                     signal_details["services_list"].extend(filter(None, offer_details))

            # Service/Product Check
            if processed_schema["Service"] or processed_schema["Product"]:
                credibility_signals["services_list"] = True
                for service in processed_schema["Service"]:
                    signal_details["services_list"].append(service.get("name") or str(service))
                for product in processed_schema["Product"]:
                     signal_details["services_list"].append(product.get("name") or str(product))

            # Review/AggregateRating Check
            if processed_schema["Review"]:
                credibility_signals["customer_reviews"] = True
                signal_details["customer_reviews"]["reviews"] = processed_schema["Review"] # Store full review objects
            if processed_schema["AggregateRating"]:
                agg = processed_schema["AggregateRating"][0] # Assume one
                if agg.get("reviewCount", 0) > 0 or agg.get("ratingValue") is not None:
                     credibility_signals["customer_reviews"] = True
                     signal_details["customer_reviews"]["aggregate"] = agg

            # --- 3. Regex Fallback for Business Info ---
            if not credibility_signals["business_info"]:
                 logger.debug("Schema did not contain business info, running regex preprocessing...")
                 preprocessed = self._preprocess_content(text_content, html_content)
                 if preprocessed["has_phone"] or preprocessed["has_address"] or preprocessed["has_hours"]:
                      credibility_signals["business_info"] = True
                      # Merge regex findings if schema was empty for these
                      if not signal_details["business_info"]["phones"]:
                           signal_details["business_info"]["phones"] = preprocessed["found_patterns"]["phones"]
                      if not signal_details["business_info"]["addresses"]:
                           signal_details["business_info"]["addresses"] = preprocessed["found_patterns"]["addresses"]
                      if not signal_details["business_info"]["hours"]:
                           signal_details["business_info"]["hours"] = preprocessed["found_patterns"]["hours"]
                      logger.debug("Found business info via regex fallback.")
                 else:
                      logger.debug("Regex preprocessing did not find business info either.")

            # --- 4. Determine Missing Signals ---
            missing_signals = [k for k, v in credibility_signals.items() if not v and k != "business_info"] # Exclude business_info here, handle it differently
            # Check if specific parts of business_info are missing even if flag is True
            if credibility_signals["business_info"]:
                 if not signal_details["business_info"]["phones"]:
                      missing_signals.append("business_info_phone")
                 if not signal_details["business_info"]["addresses"]:
                      missing_signals.append("business_info_address")
                 if not signal_details["business_info"]["hours"]:
                      missing_signals.append("business_info_hours")
            elif not credibility_signals["business_info"]: # If business_info is completely False
                 missing_signals.extend(["business_info_phone", "business_info_address", "business_info_hours"])

            # --- 5. Conditional LLM Call ---
            if missing_signals:
                logger.debug(f"Signals missing after Schema/Regex: {missing_signals}. Querying {settings.BUSINESS_CREDIBILITY_MODEL}...")
                # Get LLM
                llm, _ = get_llm(model_name=settings.BUSINESS_CREDIBILITY_MODEL, temperature=0.0)

                # Define signal mapping for prompt
                signal_prompt_map = {
                    "years_in_business": "- Years in business/establishment date",
                    "customer_reviews": "- Customer reviews/testimonials",
                    "services_list": "- Services/products offered",
                    "certifications": "- Professional certifications/licenses/awards/memberships",
                    "business_info_phone": "- Business phone number",
                    "business_info_address": "- Business physical address",
                    "business_info_hours": "- Business operating hours"
                }
                missing_signals_text = "\n".join([signal_prompt_map[s] for s in missing_signals if s in signal_prompt_map])

                # Create tailored prompt
                llm_prompt = ChatPromptTemplate.from_messages([
                    ("system", """You are an expert business analyst detecting specific missing credibility signals from website content.
                    You will be told which signals were already found via structured data or regex. Focus ONLY on finding the signals listed under 'Signals to Find'.
                    Analyze the HTML and Text content provided, paying attention to navigation, footers, contact/about sections, and common page structures.
                    Return your analysis ONLY for the requested missing signals as a clean JSON object. Be particular about each signal and ensure that the signal matches the eeat/credibility signal.
                    For example, make sure if there is an address, it is the address of the business.  If there is a phone number, it is the business phone number. 
                    If there are services, they are the services offered by the business. If there are certifications, they are the certifications/licenses/awards/memberships of the business.
                    If there are testimonials, they are the testimonials of customers about the business.
                    Do not include markdown formatting."""),
                    ("human", """\n                    Signals already found: {found_signals_summary}\n                    \n                    Signals to Find:\n                    {missing_signals_list}\n                    \n                    Analyze the website content below to find the missing signals listed above.\n                    \n                    Text Content:\n                    {text_content}\n                    \n                    HTML Content:\n                    {html_content}\n                    """)
                ])

                found_signals_summary = {k: v for k,v in credibility_signals.items() if v}

                llm_chain = llm_prompt | llm | StrOutputParser()
                llm_result_str = llm_chain.invoke({
                    "found_signals_summary": json.dumps(found_signals_summary),
                    "missing_signals_list": missing_signals_text,
                    "text_content": text_content,
                    "html_content": html_content
                })

                # Clean and parse LLM result
                llm_result_str = llm_result_str.strip().removeprefix("```json").removesuffix("```").strip()
                try:
                    llm_data = json.loads(llm_result_str)
                    logger.debug(f"LLM Analysis Result for Missing Signals: {llm_data}")

                    # Merge LLM findings
                    merged_business_info = False
                    # Map LLM response keys (descriptive) back to internal signal keys
                    llm_key_to_signal_map = {
                        "Years in business/establishment date": "years_in_business",
                        "Customer reviews/testimonials": "customer_reviews",
                        "Services/products offered": "services_list",
                        "Professional certifications/licenses/awards/memberships": "certifications",
                        "Business phone number": "business_info_phone",
                        "Business physical address": "business_info_address",
                        "Business operating hours": "business_info_hours"
                    }

                    # Iterate through the keys the LLM actually returned
                    for llm_key, detail_value in llm_data.items():
                        # Find the corresponding internal signal key
                        internal_signal = llm_key_to_signal_map.get(llm_key)

                        # Proceed if we have a mapping and the LLM provided a non-False value
                        if internal_signal and detail_value is not False:
                            # Check if this signal was originally one of the missing ones we asked for
                            if internal_signal in missing_signals or (internal_signal.startswith("business_info_") and internal_signal in missing_signals):
                                if internal_signal.startswith("business_info_"):
                                    part = internal_signal.split("_")[-1] + "s" # e.g., phones, addresses, hours
                                    # Ensure detail_value is treated as a list for business info parts
                                    value_to_append = detail_value if isinstance(detail_value, list) else [str(detail_value)]
                                    # Only set business_info to True if we actually found non-empty values
                                    if part in signal_details["business_info"] and not signal_details["business_info"][part] and value_to_append and any(value_to_append):
                                        signal_details["business_info"][part].extend(value_to_append)
                                        credibility_signals["business_info"] = True
                                        merged_business_info = True
                                elif internal_signal in credibility_signals:
                                    # Only set signal to True if we actually found non-empty values
                                    has_valid_data = False

                                    if internal_signal == "years_in_business":
                                        if isinstance(detail_value, list) and detail_value:
                                            signal_details[internal_signal] = str(detail_value[0]) # Take first item
                                            has_valid_data = True
                                        elif isinstance(detail_value, str) and detail_value.strip():
                                            signal_details[internal_signal] = detail_value
                                            has_valid_data = True
                                        elif detail_value and not isinstance(detail_value, list):
                                            signal_details[internal_signal] = "Found by LLM (Format unclear)"
                                            has_valid_data = True
                                    # For lists like services or certifications, ensure it's a list
                                    elif internal_signal in ["services_list", "certifications", "customer_reviews"]:
                                        if isinstance(detail_value, list) and detail_value:
                                            signal_details[internal_signal] = detail_value
                                            has_valid_data = True
                                        elif detail_value and not isinstance(detail_value, list): # Allow single strings for reviews too
                                            signal_details[internal_signal] = [str(detail_value)] # Wrap single item in list
                                            has_valid_data = True
                                    elif detail_value:
                                        signal_details[internal_signal] = detail_value
                                        has_valid_data = True

                                    # Only set the signal to True if we found valid data
                                    if has_valid_data:
                                        credibility_signals[internal_signal] = True

                    if merged_business_info:
                        logger.debug("Updated business_info details based on LLM findings.")

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM response for missing signals: {e} - Response: {llm_result_str[:200]}...")
                except Exception as e:
                    # Corrected f-string syntax below
                    logger.error(f"Error processing LLM response for missing signals: {e}", exc_info=True)
            else:
                 logger.debug("No missing signals found after Schema/Regex check. Skipping LLM.")

            # --- 6. Combine Results ---
            final_result = {
                "credibility_signals": credibility_signals,
                "signal_details": signal_details
            }

            logger.debug(f"Final Business credibility analysis result: {json.dumps(final_result)[:300]}..." )
            return json.dumps(final_result)

        except Exception as e:
            logger.error(f"Error in BusinessCredibilityTool _run: {str(e)}", exc_info=True)
            error_response = {
                "credibility_signals": {k: False for k in credibility_signals},
                "signal_details": {k: None for k in signal_details},
                "error": "Credibility analysis failed",
                "message": str(e)
            }
            return json.dumps(error_response)
