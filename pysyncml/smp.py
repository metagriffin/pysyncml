# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# file: $Id$
# auth: metagriffin <mg.github@uberdev.org>
# date: 2012/05/30
# copy: (C) Copyright 2012-EOT metagriffin -- see LICENSE.txt
#------------------------------------------------------------------------------
# This software is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This software is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see http://www.gnu.org/licenses/.
#------------------------------------------------------------------------------

'''
The ``pysyncml.smp`` implements a basic Stable Marriage Problem solution.
'''

from itertools import product

#------------------------------------------------------------------------------
class AsymmetricMatch(Exception): pass

#------------------------------------------------------------------------------
def match(A, B, acmpfunc, bcmpfunc):
  if len(A) == len(B):
    return match_eq(A, B, acmpfunc, bcmpfunc)
  if len(A) > len(B):
    ret = match(B, A, bcmpfunc, acmpfunc)
    return [(b, a) for (a, b) in ret]
  rank = dict()
  for a in A:
    rank[a] = sorted(B, cmp=lambda b1, b2: acmpfunc(a, b1, b2))
  bs = set()
  for idx in range(len(B)):
    for a in A:
      bs.add(rank[a][idx])
    if len(bs) < len(A):
      continue
    if len(bs) == len(A) or len(bs) > len(B):
      return match(A, bs, acmpfunc, bcmpfunc)
    # TODO: implement selective reduction of bs... for example,
    #       in the first ``idx`` elements, which ``b`` shows up the least?
    raise AsymmetricMatch('could not reduce match set')
  if isinstance(A, set) and isinstance(B, set):
    raise AsymmetricMatch('unexpected reduction input set')
  return match(set(A), set(B), acmpfunc, bcmpfunc)

#------------------------------------------------------------------------------
def match_eq(A, B, acmpfunc, bcmpfunc):
  # TODO: this is *ugly*... but ``stable`` has such an odd interface...
  if len(A) != len(B):
    return match(A, B, acmpfunc, bcmpfunc)
  A = list(A)
  B = list(B)
  indeces = range(len(A))
  rA = [sorted(indeces, cmp=lambda ib1, ib2: acmpfunc(A[ia], B[ib1], B[ib2]))
        for ia in indeces]
  rB = [sorted(indeces, cmp=lambda ia1, ia2: bcmpfunc(B[ib], A[ia1], A[ia2]))
        for ib in indeces]
  rrA = dict((('a%d'%ia, ib + 1), 'b%d'%rA[ia][ib]) for (ia, ib) in product(indeces, indeces))
  rrB = dict((('b%d'%ib, ia + 1), 'a%d'%rB[ib][ia]) for (ib, ia) in product(indeces, indeces))
  rrA.update(rrB)
  ret = stable(rrA, ['a%d'%i for i in indeces], ['b%d'%i for i in indeces])
  def getVal(val):
    if val[0] == 'a':
      return A[int(val[1:])]
    return B[int(val[1:])]
  return [(getVal(a), getVal(b)) for (a, b) in ret]

#------------------------------------------------------------------------------
# shamelessly scrubbed from:
#   https://github.com/paulgb/Python-Gale-Shapley
def stable(rankings, A, B):
  r"""
  rankings[(a, n)] = partner that a ranked n^th

  >>> from itertools import product
  >>> A = ['1','2','3','4','5','6']
  >>> B = ['a','b','c','d','e','f']
  >>> rank = dict()
  >>> rank['1'] = (1,4,2,6,5,3)
  >>> rank['2'] = (3,1,2,4,5,6)
  >>> rank['3'] = (1,2,4,3,5,6)
  >>> rank['4'] = (4,1,2,5,3,6)
  >>> rank['5'] = (1,2,3,6,4,5)
  >>> rank['6'] = (2,1,4,3,5,6)
  >>> rank['a'] = (1,2,3,4,5,6)
  >>> rank['b'] = (2,1,4,3,5,6)
  >>> rank['c'] = (5,1,6,3,2,4)
  >>> rank['d'] = (1,3,2,5,4,6)
  >>> rank['e'] = (4,1,3,6,2,5)
  >>> rank['f'] = (2,1,4,3,6,5)
  >>> Arankings = dict(((a, rank[a][b_]), B[b_]) for (a, b_) in product(A, range(0, 6)))
  >>> Brankings = dict(((b, rank[b][a_]), A[a_]) for (b, a_) in product(B, range(0, 6)))
  >>> rankings = Arankings
  >>> rankings.update(Brankings)
  >>> stable(rankings, A, B)
  [('1', 'a'), ('2', 'b'), ('3', 'd'), ('4', 'f'), ('5', 'c'), ('6', 'e')]

  """
  partners = dict((a, (rankings[(a, 1)], 1)) for a in A)
  is_stable = False # whether the current pairing (given by `partners`) is stable
  while is_stable == False:
    is_stable = True
    for b in B:
      is_paired = False # whether b has a pair which b ranks <= to n
      for n in range(1, len(B) + 1):
        a = rankings[(b, n)]
        a_partner, a_n = partners[a]
        if a_partner == b:
          if is_paired:
            is_stable = False
            partners[a] = (rankings[(a, a_n + 1)], a_n + 1)
          else:
            is_paired = True
  return sorted((a, b) for (a, (b, n)) in partners.items())

#------------------------------------------------------------------------------
# end of $Id$
#------------------------------------------------------------------------------
