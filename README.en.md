# RPG AI Assistant

[🇷🇺 Русская версия](README.md)

<img width="1200" height="749" alt="Screenshot_119" src="https://github.com/user-attachments/assets/c9b10208-0867-4675-a01b-6f78147b89c4" />

<img width="1200" height="751" alt="Screenshot_117" src="https://github.com/user-attachments/assets/bed16242-f6fa-4032-a330-4f7cc2131da0" />


# RPG Assistant — Role-playing game with local LLMs

- The script allows you to play role-playing games even using small models like **Qwen 3.5 9B**, **Qwen 3.5 35B**, **Gemma-4 e4b**.

**Who this project is for:**
- Those who need honest reasoning from the neural network with full justification of decisions.
- Those who need unlimited memory for the neural network.
- Those who want to create their own world and "bring it to life".

**Who this project is NOT for:**
- You don't know the difference between a "program" and a "neural network model".
- You want to press one button and play whatever the neural network throws at you.
- You are not ready to create your own world.

---

## 📖 Features

- **Unlimited memory** — version 0.12.0 and higher.
- **Multi-stage processing** — the program splits request processing into several stages. At each stage, the model is given a single task and a minimal `system prompt`.
- **Flexible content management** — you can create game objects, edit prompts, and change their loading order directly in the interface.
- **Does not impose decisions** — the script does not make decisions for the model, it only splits the task and passes data between steps.
- **Tool use** — the model interacts with the program via the Tools mechanism.
- **Randomness** — random events are added to make generation more interesting.
- **Multiple NPCs** — the program allows the model to handle many characters at once.
- **Unbiasedness** — each character's reaction is processed separately: the model first determines what the character "plans" to do, then combines their decisions into the prepared scene and outputs the result.
- **Full feedback**:
  - The interface shows which prompts are sent to the model.
  - Displays the entire model thinking process (including calls to the script).
  - The `logs` folder stores up to 30 logs with each model decision.
  - Ability to regenerate the last message.
- **Long-term associative memory.** The model saves information about each object and only retrieves it if the object is present in the scene.
- **Full control over the entire decision-making process**: each reasoning step can be disabled and edited.

---

## ⚙️ Installation and usage

1. **Install Python** and add it to your `PATH`.
2. **Install LM Studio**.
3. **Download a suitable model** (see requirements below).
4. **Run `install_deps.bat`** — Python dependencies will be installed.
5. **Run `run_rpg_assistant.bat`**.
6. In settings, select the model from the list.
7. Press **"Start Game"**.

---

## 🧠 Model requirements

- Supports **Tools**
- Supports **Thinking**
- Preferably **Instruct**
- Preferably **Uncensored**
- Quantization `Q4_K_M` works, `Q6` allows a bit more context.

### Recommended models
- **My recommendation:**
- **Gemma-4 e4b** — 20x faster than QWEN, but can only "think" in censored mode.
- **qwen3.5-9b-claude-4.6-os-auto-variable-heretic-uncensored-thinking-max-neocode-imatrix@q6_k**
- **Qwen 3.5 9B** — gives good results.

---

## ⚠️ Important notes on issues

- If `Thinking` starts showing **few details** — you have overloaded the model with information.
- If the model cannot call functions several times — you have overloaded the model with information.
- First, disable short-term memory.
- Reduce prompt length.
- Try regenerating the message.
- Reduce the number of messages in history to 2 and disable short-term memory.
- Temporarily disable history and other non-system prompts.
- Lower temperature to 0.3–0.5.

---

# SCRIPT LOGIC

## STAGE 0
- Player sends a message.

---

## STAGE 1 `_stage1_request_descriptions`

### Step 1.1 "Request object descriptions"

**Model receives:**
- System prompt
- Assigned prompts from the right panel in the specified order.
- Player's message (treated as the action the player intends to attempt).
- Script sends a list of all available objects (items, characters, locations) (id and names).
- Script sends associative memory information about these objects.

**Information processing:**
- Model merges this into an updated object list.
- Model decides, based on available info, what scene to play out.
- Once it knows the scene, it decides which object prompts to request from the script.
- Requests object prompts from the script via a special command.
- After receiving all info, it starts thinking about the scene, outlining general contours.
- When ready, it sends the "List of objects with descriptions" back to the script.

#### Simplified logic diagram

**Step 1.1 (First model call)**
> Get objects → Request info → Read info and determine if objects fit the scene based on available data → output validated objects

**Output:**
> "List of objects with descriptions"

### Step 1.2 "Create scene"

**Model receives:**
- System prompt
- Assigned prompts from the right panel in the specified order.
- Player's message (intended action).
- "List of objects with descriptions" — reads and filters unsuitable ones.
- Creates a scene based on the information.
- Sends scene to script via special command.

#### Simplified logic diagram

**Step 1.2 (Second model call)**
> Input validated objects → Create scene → Output scene

**Output:**
> "Scene description"

### Shared memory info:
- "List of all object names"
- "List of objects with descriptions"
- "Scene description"

### Error handling:
- If an error occurs, try to parse the result from the message.
- If no decision is made within the allowed attempts and the script returned from stage 2 twice, accept the last "List of objects".

---

## STAGE 2 Verify player truthfulness

**Model receives:**
- System prompt
- Assigned prompts from the right panel
- Player's message (intended action)

**Processing:**
- Model checks if the player is lying according to the system prompt.
- If lying, it changes the message to one that matches the reality.  
  *Example: player "opened" a locked door → becomes "attempts to open the door".*
- Sends "Edited player message" to script via special command.

**Output:**
> "Edited player message"

### Shared memory info:
- "List of all object names"
- "List of objects with descriptions"
- "Scene description"
- "Edited player message"

### Error handling:
- If an error occurs, try to parse from message.
- If no decision, take the last generated message.

---

## STAGE 3 `_stage1_player_action` "Process player action"

**Model receives:**
- System prompt
- Assigned prompts
- Player's message (intended action)
- "Scene description"
- "Edited player message"
- A set of generated d20 numbers

**Processing:**
- Describes what the player did under current conditions.
- If the player performs an action, model takes a number from the list (in order) and determines success based on dice rules.
- If no dice rules provided, simulates a roll.
- Describes what happens to the player based on the data.
- Sends description to script via special command.

**Output:**
> "Player action result"

### Shared memory info:
- "List of all object names"
- "List of objects with descriptions"
- "Scene description"
- "Player action result"

### Error handling:
- If error, try to parse.
- If no decision, take the last scenario.

---

## STAGE 4 `_stage1_random_event` "Determine if an event occurs"

**Model receives:**
- System prompt
- Assigned prompts
- "List of all object names"
- A set of generated d100 numbers

**Processing:**
- Takes a d100 number to determine event probability (system prompt defines success threshold).
- If no dice rules provided, simulates a roll.
- If unsuccessful, event handling stages are skipped.
- Sends whether event happened to script via special command.

**Output:**
> "Did the event happen"

### Shared memory info:
- "List of all object names"
- "List of objects with descriptions"
- "Scene description"
- "Player action result"
- "Did the event happen"

### Error handling:
- If error, try to parse.
- If no decision, event does not happen.

---

## STAGE 5.1 "Event happened – find additional objects"

**Model receives:**
- System prompt
- Assigned prompts
- "List of objects with descriptions"
- "List of all object names"
- Script sends associative memory info about these objects (if associative memory count for this stage is not set to 0).

**Processing:**
- Merges info into an updated object list (newest associative memory takes priority).
- Determines if current object list is enough to describe the event; if not, selects needed objects from the name list.
- Requests descriptions of new objects from the script, reads, filters unsuitable.
- Sends "New objects" to script via special command.
- Script merges old list with new into "Extended list of objects with descriptions".

**Output:**
> "Extended list of objects with descriptions"

### Shared memory info:
- "List of all object names"
- "Extended list of objects with descriptions"
- "Scene description"
- "Player action result"
- "Did the event happen"

### Error handling:
- If error, try to parse.
- If no decision, event does not happen and skip to stage 7.

#### Simplified logic diagram
> Got event info → Got object names list → Decided what's missing → Requested missing objects → Determined which fit the scene → Output object list.

---

## STAGE 5.2 "Describe event"

**Model receives:**
- System prompt
- Assigned prompts
- A set of generated d20 numbers

**Processing:**
- Rolls d20 to determine how good or bad the event is.
- Describes the event accordingly. Sends "Ready event" to script via special command.

**Output:**
> "Ready event"

### Shared memory info:
- "List of all object names"
- "Extended list of objects with descriptions"
- "Scene description"
- "Player action result"
- "Did the event happen"
- "Ready event"

---

## STAGE 6

*Script sends characters from the "Extended list of objects with descriptions" one by one*

**Model receives:**
- System prompt
- Assigned prompts
- "Scene description"
- "Extended list of objects with descriptions"
- "Player action result"
- "Ready event" (optional)
- Character to process

**Processing:**
- Model describes what the character plans to do in this situation.
- Returns "Character plan" to script via special command.
- Script adds it to "List of character plans".

**Output:**
> "List of character plans"

### Shared memory info:
- "List of all object names"
- "Extended list of objects with descriptions"
- "Scene description"
- "Player action result"
- "Did the event happen"
- "Ready event"
- "List of character plans"

### Error handling:
- If error, try to parse.
- If no decision, character planned nothing (model will handle it in the finale).

---

## STAGE 8 `_stage3_final`

**Model receives:**
- System prompt
- Assigned prompts
- "Extended list of objects with descriptions"
- "Scene description"
- "Player action result"
- "Ready event"
- "List of character plans"

**Processing:**
- Based on collected data and character desires, the model creates the story: what actually happened.
- Model sends "Final story" as plain text.

**Output:**
- "List of all object names"
- "Extended list of objects with descriptions"
- "Scene description"
- "Player action result"
- "Did the event happen"
- "Ready event"
- "List of character plans"
- "Final story"

---

## STAGE 8.1 History check

In this stage, the model cyclically checks consistency of the response against history records.

**Input:**
- Short-term memory
- Associative memory
- If "Enable history grouping: No" → list of history entries.
- If "Enable history grouping: Yes" → list of grouped histories.
- "Final story"

**Setting:** `"Number of new stories to compare with old stories: 2"`

**Important rules:**
- Each subsequent cycle receives the message changed in the previous step plus the original to monitor distortion.
- History must come as single entries: only the model's response without "Assistant" prefixes.
- User messages are ignored because they are declarations of intent, not actions.
- Tell the model how many messages passed between the history entry and the current message so it can gauge how much information may have changed.

**IMPORTANT!** Only histories whose changes the model marked as important in step 11 are checked!  
From the selected message pairs, do NOT pass the user message — only the model's response (no "Assistant:" prefix). This applies to both "new history" and "old history".  
New history should be exactly 1 item (i.e., the previous model message that the user replied to), not two.  
At each step (except the first), the original must not be passed forward.

### Example check cycle:

**Check 1:**
- Receives the oldest unchecked model message.
- Receives the newest model message (last sent).
- Receives the Final result.
- Oldest unchecked message is compared with newest model message. Any contradictions resolved in favor of the newest message → "General info".
- "General info" is compared with Final. Contradictions resolved in favor of "General info" with minimal necessary changes to Final.
- Output "Final info".

**Check 2:**
- Receives oldest unchecked model message.
- Receives newest model message.
- Receives "Final info" as Final.
- Continue similarly...

### Detailed check cycle

**Cycle 1 (model receives a separate request):**
1.1 Input: "associative memory", newest history or history group (amount as per settings). High priority given to newest history/group.
1.2 Check consistency of info with the message. *Example inconsistency: in "associative memory" door is locked, but in the response it's open.*
1.3 Make minimal edits to the final response.
1.4 Output response.

**Cycle 2 (model receives a separate request):**
2.1 Input: "short-term memory", newest history/group (amount as per settings). High priority for newest.
2.2 Check consistency. Since this is the farthest memory, look only for very coarse errors. *Example coarse violation: player beat a troll in a fistfight, but the message calls them a novice in fighting.*
2.3 Apply minimal edits.
2.4 Output.

**Cycle 3 (model receives a separate request):**  
Model receives memory pairs: user response, model response to that query — not individually!
3.1 Input: the last (most distant in time) unchecked history/group **AND** the newest history/group (amount as per settings). High priority to newest.
3.2 Check consistency.
3.3 Apply minimal edits.
3.4 Output.

**Cycle 3 repeats** until all histories/groups in the list have been checked. Each time the model receives a new request.  
These requests should be logged and shown in the central window. Thoughts in the Thinking panel. Progress in the message output panel.

---

## STAGE 8.2 Validation

### Validation algorithm:
1. Characters participating in the scene must either have been involved in the history before or their absence must be logically justified.
2. Character plans must match the final output.
3. Player action must match its processing and output.
4. Actions must match dice roll results.
5. Model must not substitute dice with its own values.
6. Check consistency with the setting from description and history.
7. Check for logical inconsistencies.
8. Response must contain specifics instead of generalizations.

*Minor imperfections can be ignored.*  
This step must receive all necessary information for validation.  
If the step approves the history, it passes it forward.

---

## STAGE 9

Script sends a new message to the model.

**Model receives:**
- Final story
- Model makes a brief summary of what happened and outputs text.

**Output:**
- Dictionary of character plans
- List of objects + New objects (optional)
- List of all object names
- Player action result
- Ready event (optional)
- Final story
- Brief summary of what happened

---

## STAGE 10 Associative memory

Script sends a new message to the model.

**Model receives:**
- Final story
- List of objects + New objects (optional)

Model determines changes and important events that happened to objects. Similar to stage 9, it creates a brief summary and outputs it as text.

**Output:**
- Dictionary of character plans
- List of objects + New objects (optional)
- List of all object names
- Player action result
- Ready event (optional)
- Final story
- Brief summary
- Associative memory about objects

Script saves these changes in the session file. The number of such entries is configurable. Old entries are deleted.

---

## STAGE 11 Check for significant changes in history

**Input:**
- previous pair "User request – model response"
- current pair "User request – model response"

**Action:**
- Model looks for significant changes between the two histories.
- Outputs a flag: changes exist or not.

Script records in sessions whether important changes occurred (yes/no).

> **Note:** initially try cyclic processing only, to avoid overcomplicating.

---

## STAGE 12 Compress memory into "History groups"

*Detailed in "Logic: Memory compression"*

---

## Logic: Memory compression

### Example settings:
- Maximum memory sent per stage: **12**
- Enable history grouping: **yes**
- Memory size per group: **5**
- Number of new stories to compare with old stories: **2**

In this example, the number of groups passed to the model is `12 / 5` rounded up = **3 groups**:
- "History group 1" — up to 5 merged stories
- "History group 2" — up to 5 merged stories
- "History group 3" — up to 2 merged stories (12/5 = 2 groups with remainder 2 messages in group 3)

### Sequence:

**0. Game start**

**RESPONSE 1**
1.1 I write a message  
1.2 Model replies  
1.3 My and its responses added to history in sessions "History 1"  
1.4 Model writes (duplicates) "History 1" into session "History group 1"

**RESPONSE 2**
2.1 I write a message  
Model receives "History group 1" as input  
2.2 Model replies  
2.3 My and its responses added to "History 2"  
2.4 Model merges "History group 1" and "History 2" into one "History group 1", compressing into facts:
- Player action. Result. Character 1 reaction. Character 2 reaction... etc. Object changes (location, item, character) caused by this action.
- Character action. Result. Player reaction. Character 1 reaction... etc. Object changes caused by this action.

**RESPONSE 3**
3.1 I write a message  
3.2 Model replies  
3.3 Added to "History 3"  
3.4 Model merges "History group 1" and "History 3" into one "History group 1", compressing to facts.

**RESPONSE 4** similarly  
**RESPONSE 5** similarly  

**RESPONSE 6** — a new memory block "History group 2" is created (because setting "Memory size per group = 5").

---

## General notes

- **Tools:** used to transfer data between model and script at all stages.
- **Retries:** on errors, model tries to parse the message; if no decision after allowed attempts, the last valid value or default fallback is used.
- **System prompts:** set separately for each stage and always added last to the prompt list.

## 📁 Log structure

- `logs` folder — stores up to 30 recent logs describing each model decision.

---

## 💡 Tip

- Tested working with `qwen3.5-9b-claude-4.6-os-auto-variable-heretic-uncensored-thinking-max-neocode-imatrix@q6_k`
