#include "common.h"
#include "b3/CGtPolygonSoup.h"

void CGtPolygonSoup::FixUp()
{
    // By performing the entire operation for m_pMember1 in one statement,
    // we encourage the compiler to use and then discard the temporary register.
    this->m_pMember1 = reinterpret_cast<Member1*>((uint32_t)this + (uint32_t)this->m_pMember1);

    // This allows the compiler to reuse the same register for the second operation,
    // which is key to matching the original assembly. The compiler is then
    // smart enough to place the final 'store word' into the branch delay slot.
    this->m_pMember2 = reinterpret_cast<Member2*>((uint32_t)this + (uint32_t)this->m_pMember2);
}

// void CGtPolygonSoup__FixUp(int32_t *a1)
// {
//   *a1 += (int32_t)a1;
//   a1[1] += (int32_t)a1;
// }