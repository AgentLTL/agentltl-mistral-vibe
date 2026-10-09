# Mistral Vibe, for trying the AgentLTL plugin end to end (see the README, "Development"):
#
#   docker/e2e.sh                # a scripted model, no model needed
#   docker/live.sh "a task"      # your OpenAI-compatible model, from .env (.env.example)
#
# The Vibe version is pinned in requirements.txt. /work is a scratch git repository; the
# entrypoint points Vibe at the model in VLLM_*.
FROM python:3.12-slim
COPY requirements.txt /opt/agentltl/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r /opt/agentltl/requirements.txt
RUN useradd -m dev && mkdir /work /probe && chown dev /work /probe
USER dev
ENV PATH="/home/dev/.local/bin:${PATH}"
RUN git config --global user.name dev && git config --global user.email dev@example.com \
    && git config --global init.defaultBranch main && git -C /work init -q
COPY --chown=dev entrypoint.sh probe.py /opt/agentltl/
WORKDIR /work
ENTRYPOINT ["/opt/agentltl/entrypoint.sh"]
CMD ["bash"]
