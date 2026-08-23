from nodes.or_text import ORTextEcho, ORTextLLM

#print(ORTextEcho.INPUT_TYPES())
#print(ORTextEcho.RETURN_TYPES)

# test method
#print(ORTextEcho().run_text("router", "hello hahah"))


question = "hi who are you and which model you are"
model = "qwen/qwen3.7-flash"

print(ORTextLLM().run_main(your_api_key="", system_prompt="", user_prompt=question,
         model=model, temperature=1, max_tokens=3000))



