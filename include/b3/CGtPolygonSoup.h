// include/CGtPolygonSoup.h
#ifndef CGTPOLYGONSOUP_H
#define CGTPOLYGONSOUP_H

//#include <stdint.h> // For intptr_t

struct Member1
{
    int data1;
};

struct Member2
{
    int data1;
};

class CGtPolygonSoup16 {
public:
    void FixUp();
    
    // We deduce these members from the assembly.
    // The names are placeholders until you discover what they are.
    Member1* m_pMember1; // at offset 0x0
    Member2* m_pMember2; // at offset 0x4
    // ... other members might follow
};

class CGtPolygonSoup {
public:
    void FixUp();

    // We deduce these members from the assembly.
    // The names are placeholders until you discover what they are.
    Member1* m_pMember1; // at offset 0x0
    Member2* m_pMember2; // at offset 0x4
    // ... other members might follow
};

#endif // CGTPOLYGONSOUP_H