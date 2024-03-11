from party.llm_party import Party as Party_LLM
from loguru import logger
from .LocalCommunication import LocalCommunication


class QW_Passive_Party(Party_LLM):
    _communication = None

    def __init__(self, args, index):
        super().__init__(args, index)

    def prepare_data(self, args, index):
        pass

    def predict(self, **kwargs):
        intermediate = self.local_model.forward(**self._format_forward_kwargs(**kwargs))[0]
        logger.debug('finish passive party')
        logger.debug(intermediate.hidden_states[-1])
        if isinstance(self._communication, LocalCommunication):
            return intermediate
        return {
            "hidden_states": intermediate.hidden_states[0].tolist(),
            "attention_mask": intermediate.attention_mask[0].tolist(),
            "past_key_values": intermediate.past_key_values[0],
            "output_hidden_states": intermediate.output_hidden_states,
            "position_ids": intermediate.position_ids[0].tolist()
        }

    def init_communication(self, communication=None):
        if communication is None:
            communication = LocalCommunication(self.args.parties[self.args.k - 1])
        self._communication = communication

    def _format_forward_kwargs(self, **kwargs):
        if not kwargs:
            tokenizer = self.args.tokenizer
            prompt = "You are a python programmer, what can you do?"
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            model_inputs = tokenizer([text], return_tensors="pt")
            kwargs.update({'input_ids': model_inputs.input_ids,
                           'output_hidden_states': True})
            logger.debug(f"default inference, kwargs.keys: {kwargs.keys()}")
        base_dict = {'input_ids': None,
                     'attention_mask': None,
                     'position_ids': None,
                     'past_key_values': None,
                     'inputs_embeds': None,
                     'use_cache': False,
                     'output_attentions': None,
                     'output_hidden_states': True,
                     'return_dict': None, }
        for k in base_dict:
            if k in kwargs:
                base_dict.update({k: kwargs.get(k)})
        return base_dict

    def __call__(self, *args, **kwargs):
        return self.predict(**kwargs)