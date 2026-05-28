"""Pure Glicko-2 rating algorithm implementation.

Reference: Glickman, M.E. (2012). Example of the Glicko-2 system.
http://www.glicko.net/glicko/glicko2.pdf
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class GlickoPlayer:
    mu: float = 1500.0  # rating (display scale)
    phi: float = 350.0  # rating deviation (RD)
    sigma: float = 0.06  # volatility


class Glicko2System:
    TAU = 0.5  # system constant; controls volatility change speed
    SCALE = 173.7178  # conversion factor between display and internal scale
    EPSILON = 1e-6  # convergence threshold for Illinois algorithm

    @staticmethod
    def _to_internal(mu: float, phi: float) -> tuple[float, float]:
        """Convert display-scale (μ, φ) to internal (μ', φ')."""
        mu_prime = (mu - 1500.0) / Glicko2System.SCALE
        phi_prime = phi / Glicko2System.SCALE
        return mu_prime, phi_prime

    @staticmethod
    def _to_display(mu_prime: float, phi_prime: float) -> tuple[float, float]:
        """Convert internal (μ', φ') back to display scale."""
        mu = mu_prime * Glicko2System.SCALE + 1500.0
        phi = phi_prime * Glicko2System.SCALE
        return mu, phi

    @staticmethod
    def _g(phi: float) -> float:
        """g(φ) function — reduces impact of opponents with high RD."""
        return 1.0 / math.sqrt(1.0 + 3.0 * phi**2 / math.pi**2)

    @staticmethod
    def _E(mu: float, mu_j: float, phi_j: float) -> float:
        """Expected score E(μ, μ_j, φ_j)."""
        return 1.0 / (1.0 + math.exp(-Glicko2System._g(phi_j) * (mu - mu_j)))

    @classmethod
    def update(
        cls,
        player: GlickoPlayer,
        results: list[tuple[GlickoPlayer, float]],
    ) -> GlickoPlayer:
        """Apply one Glicko-2 rating period update.

        Args:
            player: The player being updated.
            results: List of (opponent, score) where score is 1=win, 0=loss, 0.5=draw.

        Returns:
            New GlickoPlayer with updated ratings.
        """
        mu, phi = cls._to_internal(player.mu, player.phi)
        sigma = player.sigma

        if not results:
            # No games: only RD inflation (step 6, simplified)
            phi_star = math.sqrt(phi**2 + sigma**2)
            new_mu, new_phi = cls._to_display(mu, phi_star)
            return GlickoPlayer(mu=new_mu, phi=new_phi, sigma=sigma)

        # Precompute g_j, E_j for each opponent
        opponents = []
        for opp, score in results:
            mu_j, phi_j = cls._to_internal(opp.mu, opp.phi)
            g_j = cls._g(phi_j)
            E_j = cls._E(mu, mu_j, phi_j)
            opponents.append((g_j, E_j, score))

        # Step 3: compute v (estimated variance)
        v = 1.0 / sum(g**2 * E * (1 - E) for g, E, _ in opponents)

        # Step 4: compute Δ (estimated improvement)
        delta = v * sum(g * (s - E) for g, E, s in opponents)

        # Step 5: compute new volatility σ' via Illinois root-finding
        sigma_new = cls._compute_sigma(sigma, phi, v, delta)

        # Step 6: update φ* (pre-rating-period RD)
        phi_star = math.sqrt(phi**2 + sigma_new**2)

        # Step 7: update φ'
        phi_new = 1.0 / math.sqrt(1.0 / phi_star**2 + 1.0 / v)

        # Step 8: update μ'
        mu_new = mu + phi_new**2 * sum(g * (s - E) for g, E, s in opponents)

        # Step 9: convert back to display scale
        new_mu, new_phi = cls._to_display(mu_new, phi_new)
        return GlickoPlayer(mu=new_mu, phi=new_phi, sigma=sigma_new)

    @classmethod
    def _compute_sigma(cls, sigma: float, phi: float, v: float, delta: float) -> float:
        """Compute new volatility using the Illinois algorithm (Step 5)."""
        tau = cls.TAU
        a = math.log(sigma**2)

        def f(x: float) -> float:
            ex = math.exp(x)
            d2 = phi**2 + v + ex
            return ex * (delta**2 - phi**2 - v - ex) / (2.0 * d2**2) - (x - a) / tau**2

        # Initial bracket
        A = a
        if delta**2 > phi**2 + v:
            B = math.log(delta**2 - phi**2 - v)
        else:
            k = 1
            while f(a - k * tau) < 0:
                k += 1
            B = a - k * tau

        fA = f(A)
        fB = f(B)

        # Illinois algorithm
        while abs(B - A) > cls.EPSILON:
            C = A + (A - B) * fA / (fB - fA)
            fC = f(C)

            if fC * fB < 0:
                A = B
                fA = fB
            else:
                fA /= 2.0

            B = C
            fB = fC

        return math.exp(A / 2.0)
