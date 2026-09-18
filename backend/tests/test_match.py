"""Matching rules, each pinned by a real title that once produced a wrong verdict."""

import pytest

from aslideal.match import identity, same_product, search_query, tokens

AIRDOPES = "boAt Airdopes Prime 412, 4Mics AI-ENx Tech, 50 Hrs Battery, Multipoint Connectivity (Midnight Black)"
NOISE = "Noise Pro 6 Smart Watch:Intelligent AI, Endless AI Watch Faces, AI Companion"
PHILIPS = "Philips HL7756 Mixer Grinder 750W, with 3 Stainless Steel Jars"
REDMI = "Redmi Note 14 Pro 5G Titan Black 8GB RAM 128GB ROM(Without Offer)"


@pytest.mark.parametrize("candidate", [
    "boAt Airdopes Prime 412 | 50H Wireless Earbuds with AI-ENx Lunar White",
    "Buy boAt Airdopes Prime 412 Earbuds — Nalanda Enterprises Lunar White",
    "boAt Airdopes Prime 412, AI-ENx Tech, 50 Hour Battery ...",
])
def test_same_earbuds_from_other_sellers_match(candidate):
    assert same_product(AIRDOPES, candidate, "boAt")


@pytest.mark.parametrize("candidate", [
    "boAt Rockerz 412",                      # same number, different product line
    "boAt Airdopes Prime 413",               # next model
    "boAt Airdopes Prime 412 Pro",           # tier the reference lacks
    "Sounce Earphone Case Cover Compatible with Boat Airdopes Prime 412",
    "boAt Airdopes Prime 412 (Renewed)",
])
def test_other_products_and_accessories_do_not_match(candidate):
    assert not same_product(AIRDOPES, candidate, "boAt")


def test_words_must_be_in_order_and_describe_the_same_kind_of_thing():
    assert same_product(NOISE, "Noise Pro 6 1.85'' Amoled Dispay with AI Watch Faces", "Noise")
    assert not same_product(NOISE, "Noise Air Buds Pro 6 Truly Wireless Earbuds", "Noise")
    assert not same_product(NOISE, "Noise ColorFit Pro 6 Max", "Noise")
    assert not same_product(NOISE, 'Noise Pro 6R 1.46" AMOLED Smart Watch', "Noise")


def test_plus_is_a_different_phone():
    assert tokens("Note 14 Pro+ 5G") == ["note", "14", "pro", "plus", "5g"]
    assert not same_product(REDMI, "Redmi Note 14 Pro+ 5G 8GB 128GB Spectre Blue", "Redmi")


def test_memory_must_match_when_the_reference_states_it():
    assert same_product(REDMI, "Redmi Note 14 Pro 5G ( Phantom Purple , 8GB / 128GB )", "Redmi")
    assert same_product(REDMI, "REDMI Note 14 Pro 5G (128 GB, 8 GB RAM)", "Redmi")
    assert not same_product(REDMI, "Redmi Note 14 Pro 5G Ivy Green 8GB RAM 256GB ROM", "Redmi")
    assert not same_product(REDMI, "Redmi Note 14 Pro 5G", "Redmi")  # can't tell which variant


def test_real_product_names_with_part_words_still_match():
    # 'Motor' and 'Jar' describe this mixer; spare parts are caught by price instead.
    assert same_product(PHILIPS, "Mixer Grinder Philips 3 Jar 750W Turbo Motor HL7756/01", "PHILIPS")
    assert not same_product(PHILIPS, "Philips Viva Collection HR1832/00 1.5-Litre 500-Watt Juicer", "PHILIPS")


def test_no_brand_means_no_match():
    assert not same_product(AIRDOPES, "boAt Airdopes Prime 412", "")


def test_identity_and_query():
    assert identity(REDMI, "Redmi") == ["note", "14", "pro"]
    assert identity(AIRDOPES, "boAt") == ["airdopes", "prime", "412"]
    assert search_query(AIRDOPES, "boAt") == "boAt Airdopes Prime 412"
    assert search_query(PHILIPS, "PHILIPS") == "PHILIPS HL7756 Mixer"
