"""
dqn_agent.py - Agente Deep Q-Learning (DQN) implementado em PyTorch.
"""

import random
from collections import deque
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


class QNetwork(nn.Module):
    """Rede Neural que estima os valores Q(s, a)."""

    def __init__(self, state_size: int, action_space: int = 3):
        super(QNetwork, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(state_size, 64),
            nn.LayerNorm(64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.LayerNorm(64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, action_space)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DQNAgent:
    """
    Agente DQN com Experience Replay aleatório e Target Network.
    """

    def __init__(
        self,
        state_size: int,
        action_space: int = 3,
        gamma: float = 0.95,
        lr: float = 0.0005,
        epsilon_start: float = 1.0,
        epsilon_min: float = 0.02,
        epsilon_decay: float = 0.995,
        memory_size: int = 5000,
        device: str = None,
    ):
        self.state_size = state_size
        self.action_space = action_space
        self.gamma = gamma
        self.epsilon = epsilon_start
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay

        self.device = torch.device(
            device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        )

        # Redes Principal e Alvo (Target Network para estabilidade)
        self.policy_net = QNetwork(state_size, action_space).to(self.device)
        self.target_net = QNetwork(state_size, action_space).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=lr)
        self.criterion = nn.SmoothL1Loss()  # Huber loss para estabilidade contra outliers

        self.memory = deque(maxlen=memory_size)

    def act(self, state: np.ndarray, evaluate: bool = False) -> int:
        """Escolhe uma ação seguindo a política epsilon-greedy."""
        if not evaluate and random.random() <= self.epsilon:
            return random.randrange(self.action_space)

        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        self.policy_net.eval()
        with torch.no_grad():
            q_values = self.policy_net(state_t)
        return int(torch.argmax(q_values).item())

    def remember(self, state, action, reward, next_state, done):
        """Armazena a transição no buffer de experiência."""
        self.memory.append((state, action, reward, next_state, done))

    def replay(self, batch_size: int = 32) -> float:
        """Treina a rede neural usando uma amostra aleatória da memória."""
        if len(self.memory) < batch_size:
            return 0.0

        # Amostragem verdadeiramente aleatória (quebra correlação temporal)
        minibatch = random.sample(self.memory, batch_size)

        states = torch.FloatTensor(np.array([t[0] for t in minibatch])).to(self.device)
        actions = torch.LongTensor([t[1] for t in minibatch]).unsqueeze(1).to(self.device)
        rewards = torch.FloatTensor([t[2] for t in minibatch]).unsqueeze(1).to(self.device)
        next_states = torch.FloatTensor(np.array([t[3] for t in minibatch])).to(self.device)
        dones = torch.FloatTensor([1.0 if t[4] else 0.0 for t in minibatch]).unsqueeze(1).to(self.device)

        self.policy_net.train()

        # Q(s, a) atual
        current_q = self.policy_net(states).gather(1, actions)

        # Target Q = r + gamma * max_a' Q_target(s', a')
        with torch.no_grad():
            max_next_q = self.target_net(next_states).max(1)[0].unsqueeze(1)
            target_q = rewards + (1.0 - dones) * self.gamma * max_next_q

        loss = self.criterion(current_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        # Clip de gradiente para evitar explosões
        nn.utils.clip_grad_norm_(self.policy_net.parameters(), max_norm=1.0)
        self.optimizer.step()

        # Decaimento do epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

        return float(loss.item())

    def update_target_network(self):
        """Atualiza a Target Network com os pesos da Policy Network."""
        self.target_net.load_state_dict(self.policy_net.state_dict())

    def save(self, filepath: str):
        """Salva os pesos do modelo."""
        torch.save(self.policy_net.state_dict(), filepath)

    def load(self, filepath: str):
        """Carrega os pesos do modelo."""
        self.policy_net.load_state_dict(torch.load(filepath, map_location=self.device))
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.policy_net.eval()
