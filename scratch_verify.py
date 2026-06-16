import json

for filename in ["review_TCC_CCO-6_openai_gpt-5.5.json", "review_TCC_CCO-7_openai_gpt-5.5.json", "review_TCC_CCO-8_openai_gpt-5.5.json"]:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        print(f"File: {filename}")
        corpo = data.get("corpo_do_trabalho", {})
        has_any_obs = False
        for sec_name, sec_val in corpo.items():
            revisor_list = sec_val.get("revisor", [])
            for r in revisor_list:
                for idx, obs_dict in r.items():
                    normativas = obs_dict.get("observacao_normativa", [])
                    semanticas = obs_dict.get("observacao_semantica", [])
                    if normativas or semanticas:
                        print(f"  Section {sec_name}: {len(normativas)} normative, {len(semanticas)} semantic")
                        has_any_obs = True
        
        general = data.get("general", {}).get("revisor", [{}])[0].get("1", {})
        gen_sem = general.get("observacao_semantica", [])
        print(f"  General/Conclusion: {len(gen_sem)} items")
        
        if not has_any_obs:
            print("  WARNING: NO section observations parsed!")
    except Exception as e:
        print(f"Error reading {filename}: {e}")
