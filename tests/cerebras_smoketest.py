import os
from cerebras.cloud.sdk import Cerebras

client = Cerebras(
    # This is the default and can be omitted
    api_key="csk-p2yfcrypk68wkev8tjnhen3kdpc84tetyhr5jrtvj9jcjmtm"
)

stream = client.chat.completions.create(
    messages=[
        {
            "role": "system",
            "content": ""
        },
        {
            "role": "user",
            "content": "hey"
        },
        {
            "role": "assistant",
            "content": "hey"
        },
        {
            "role": "assistant",
            "content": "How's it going? Is there something I can help you with or would you like to chat?"
        }
    ],
    model="llama3.1-8b",
    stream=True,
    max_completion_tokens=2048,
    temperature=0.2,
    top_p=1
)

for chunk in stream:
  print(chunk.choices[0].delta.content or "", end="")